# ruff: noqa: E402 -- original entry anchors and exact source import setup precede later imports.
"""Bounded invented control tests; the pair case invokes both actual workers."""

from __future__ import annotations
import os
from pathlib import Path
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_terminal_parent as pair

tc = pair.tc


def put(path, value, raw=False):
    data = value if raw else tc.canonical(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            assert n > 0
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return pair.digest(data)


def case(root):
    root.mkdir(mode=0o700)
    allocation, records = root / "allocation", root / "records"
    allocation.mkdir(mode=0o700)
    records.mkdir(mode=0o700)
    put(allocation / "one.bin", b"INVENTED ONLY\x00" * 20, True)
    put(records / "slurm.log", b"INVENTED source log\n", True)
    fifo = allocation / "supervisor_wait.fifo"
    os.mkfifo(fifo, 0o600)
    start = time.time_ns() - 1_000_000_000
    end = time.time_ns() + 120_000_000_000
    limits = dict(
        members=64,
        payload_bytes=1048576,
        manifest_bytes=262144,
        record_bytes=4096,
        path_bytes=512,
        name_bytes=255,
        depth=16,
        sort_records=2,
        sort_buffer_bytes=16384,
        merge_fan_in=2,
        chunk_bytes=4096,
        wire_bytes=2097152,
        read_bytes=33554432,
        write_bytes=33554432,
        creations=512,
        operations=100000,
        scanned_entries=2048,
        seconds=20,
    )
    template = dict(
        version=tc.FIFO_VERSION,
        scope="TEST_ONLY_INVENTED",
        state="TEMPLATE",
        approval_sha256=None,
        job_id="ORIGINAL_JOB_ID",
        source_git_sha="0" * 40,
        source_uid=os.geteuid(),
        source_gid=os.getegid(),
        roots=[
            dict(label="allocation", path=str(allocation)),
            dict(label="records", path=str(records)),
        ],
        external_files=[],
        required_logs=["records/slurm.log"],
        inert_fifos=[dict(path="allocation/supervisor_wait.fifo", identity=None)],
        limits=limits,
        valid_until_epoch_ns=end,
    )
    template_path = root / "template.record"
    template_sha = put(template_path, template)
    original = dict(
        version="stage12_ra_g1_rep_first64_512_allocation_selection_v1",
        scope="REPRESENTATIVE_NO_SERVICE",
        source_sha="0" * 40,
        paths=dict(
            output=str(allocation),
            allocation_root=str(allocation),
            records=str(records),
            source=str(ROOT),
            tail=str(root / "missing-tail"),
            input=str(root / "missing-input"),
            supervisor_state=str(root / "missing-supervisor"),
        ),
    )
    original_path = root / "original-selection.record"
    original_sha = put(original_path, original)
    raw_scheduler = b"0|FAILED|1:0\n"
    raw_scheduler_path = root / "original-scheduler.raw"
    raw_scheduler_sha = put(raw_scheduler_path, raw_scheduler, True)
    terminal = dict(
        version=pair.TERMINAL_VERSION,
        job_id=0,
        source_git_sha="0" * 40,
        workload_selection_sha256=original_sha,
        scope="PUBLIC_SYNTHETIC_ONLY",
        scheduler_state="FAILED",
        exit_code=1,
        signal=0,
        raw_scheduler_sha256=raw_scheduler_sha,
        observed_epoch_ns=time.time_ns(),
    )
    terminal_path = root / "original-terminal.record"
    terminal_sha = put(terminal_path, terminal)
    authority = dict(
        version=pair.AUTH_VERSION,
        scope=pair.TEST,
        state="TEST_ONLY",
        grant_nonce="7" * 32,
        adoption_sha256=None,
        environment_gate_sha256=None,
        source_git_sha="0" * 40,
        original_job_id=0,
        original_scheduler_sha256=raw_scheduler_sha,
        original_log_policy_sha256=pair.digest(
            tc.canonical(
                dict(
                    external_files=template["external_files"],
                    required_logs=template["required_logs"],
                )
            )
        ),
        max_collection_jobs=1,
        max_collection_seconds=1800,
        collection_pool_bytes=25769803776,
        collection_pool_creations=450000,
        control_pool_bytes=67108864,
        window_start_epoch_ns=start,
        valid_until_epoch_ns=end,
    )
    authority_path = root / "authority.record"
    authority_sha = put(authority_path, authority)
    verifier = ROOT / "scripts/stage12_ra_g1_terminal_verify.py"
    binding = dict(
        version=pair.VERSION,
        scope=pair.TEST,
        state="TEST_ONLY",
        grant_nonce="7" * 32,
        authority_sha256=authority_sha,
        original_job_id=0,
        original_source_git_sha="0" * 40,
        source_git_sha="0" * 40,
        helper_sha256=pair.digest(Path(tc.__file__).read_bytes()),
        parent_sha256=pair.digest(Path(pair.__file__).read_bytes()),
        interpreter_path=sys.executable,
        selection_template_path=str(template_path),
        selection_template_sha256=template_sha,
        original_terminal_path=str(terminal_path),
        original_terminal_sha256=terminal_sha,
        original_scheduler_path=str(raw_scheduler_path),
        original_scheduler_sha256=raw_scheduler_sha,
        original_log_policy=dict(
            external_files=template["external_files"],
            required_logs=template["required_logs"],
        ),
        original_log_policy_sha256=authority["original_log_policy_sha256"],
        original_selection_path=str(original_path),
        original_selection_sha256=original_sha,
        allocation_producer_sha256=pair.digest(
            (ROOT / "scripts/stage12_ra_g1_allocation.py").read_bytes()
        ),
        verifier_path=str(verifier),
        verifier_sha256=pair.digest(verifier.read_bytes()),
        output_path=str(root / "pair"),
        seconds=30,
        window_start_epoch_ns=start,
        valid_until_epoch_ns=end,
        allowed_inert_fifo_paths=["allocation/supervisor_wait.fifo"],
        collection_external_logs=[
            dict(label="slurm_stdout", path=str(root / "collection.stdout")),
            dict(label="slurm_stderr", path=str(root / "collection.stderr")),
        ],
    )
    return binding, authority, template, terminal


def copy_stream(source, target):
    src = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    dst = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        while raw := os.read(src, 65536):
            view = memoryview(raw)
            while view:
                n = os.write(dst, view)
                assert n > 0
                view = view[n:]
        os.fsync(dst)
    finally:
        os.close(dst)
        os.close(src)


def test_actual_pair_fifo_transport_receipt_and_final_log_boundary(
    tmp_path, monkeypatch
):
    # Real test source-entry precedes all fixture setup; no fake or reset clock.
    entered = time.monotonic_ns()
    epoch = time.time_ns()
    monkeypatch.setattr(pair, "_ENTRY_MONO_NS", entered)
    monkeypatch.setattr(pair, "_ENTRY_EPOCH_NS", epoch)
    binding, authority, template, terminal = case(tmp_path / "case")
    binding_path = tmp_path / "case/binding.record"
    binding_sha = put(binding_path, binding)
    root = tmp_path / "case"
    output = root / "pair"
    # Real hosts have separate directory namespaces; prepare the invented local
    # destination before the remote pair starts, preserving all source fences.
    local = root / "local"
    local.mkdir(mode=0o700)
    transport_controls = root / "transport-controls"
    transport_controls.mkdir(mode=0o700)
    errors = []
    worker_results = []
    stop_transport = threading.Event()

    def transport():
        try:
            deadline = time.monotonic() + 20
            path = output / "TRANSPORT_READY.record"
            while not path.exists():
                if stop_transport.is_set():
                    worker_results.append(
                        {"status": "ABORTED_AFTER_PRIMARY_TEST_FAILURE"}
                    )
                    return
                assert time.monotonic() < deadline
                time.sleep(0.01)
            ready = tc.parse(path.read_bytes())
            ready_sha = pair.digest(tc.canonical(ready))
            import stage12_ra_g1_terminal_transport as adapter

            # Actual adapter and finite real producer children; no SSH/native facts.
            owner = pair.Control(entered, pair.WINDOW_END_NS, 60)
            original_monotonic_deadline = owner.end
            receipt, transport_report = adapter.fetch_ready(
                ready,
                ready_sha,
                local,
                transport_controls,
                testing_command_factory=lambda row: ["/bin/cat", row["path"]],
                control=owner,
            )
            assert transport_report["artifacts"] and not owner.cleanup_uncertain
            assert owner.end == original_monotonic_deadline == entered + 60 * 10**9
            assert owner.epoch_end == min(
                pair.WINDOW_END_NS, ready["context"]["parent_deadline_epoch_ns"]
            )
            pub = pair.Control(
                time.monotonic_ns(), ready["context"]["parent_deadline_epoch_ns"], 20
            )
            pub.record(Path(ready["local_receipt_path"]), receipt)
            worker_results.append(ready)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=transport, name="invented-local-retention")
    thread.start()
    try:
        code = pair.main(
            [
                "run-pair",
                "--binding",
                str(binding_path),
                "--binding-sha256",
                binding_sha,
                "--authority",
                str(root / "authority.record"),
                "--authority-sha256",
                binding["authority_sha256"],
                "--offline-invented",
                "--test-root",
                str(root),
            ]
        )
    finally:
        stop_transport.set()
        thread.join(timeout=2)
    assert code == 0
    result = tc.parse((output / "PAIR_PROVISIONAL_COMPLETE.record").read_bytes())
    assert not thread.is_alive() and not errors
    assert (
        len(worker_results) == 1
        and worker_results[0].get("version") == pair.READY_VERSION
    )
    fs = tc.parse((output / "FILESYSTEM_OBSERVATION.record").read_bytes())
    assert fs["scope"] == "FILESYSTEM_REPORTED_NOT_RESERVED"
    assert fs["capacity_or_native_containment_guarantee"] is False
    assert fs["acquisition_enter_mono_ns"] <= fs["acquisition_exit_mono_ns"]
    assert fs["acquisition_exit_mono_ns"] <= min(
        row["popen_enter_ns"] for row in result["child_lifecycle"]
    )
    assert fs["derived_available_unreserved_bytes"] > 0
    assert result["children_joined"] is True and result["exits"] == {
        "receive": 0,
        "export": 0,
    }
    assert result["workload_verification_complete"] is False
    assert result["candidate_native_eligible"] is False
    assert result["native_or_scientific_acceptance"] is False
    ack = tc.parse((output / "RETENTION_RECEIPT_ACK.record").read_bytes())
    assert ack["status"] == "RETENTION_RECEIPT_DURABLY_ACKNOWLEDGED"
    assert (
        tc.canonical(ack["receipt"])
        == (root / "local/RETENTION_RECEIPT.record").read_bytes()
    )
    assert pair.digest(tc.canonical(ack["receipt"])) == ack["receipt_sha256"]
    assert pair.digest(tc.canonical(ack)) == result["receipt_ack_sha256"]
    assert (
        result["context"]["original_job_id"]
        == result["context"]["collection_job_id"]
        == 0
    )
    assert (output / "receive/inert-metadata/fifo0000.record").is_file()
    assert not (output / "receive/originals/allocation/supervisor_wait.fifo").exists()
    assert all(
        row["observed_exit_ns"] < row["deadline_ns"]
        for row in result["child_lifecycle"]
    )
    assert all(
        row["joined_ns"] < row["deadline_ns"] for row in result["child_lifecycle"]
    )
    # Explicitly invented postterminal facts; no scheduler or native PASS is fabricated.
    ctx = result["context"]
    logs = []
    local_logs = root / "local-logs"
    local_logs.mkdir(mode=0o700)
    for remote_name, local_name in [
        ("TRANSPORT_READY.record", "transport-ready.original"),
        ("RETENTION_RECEIPT.record", "retention-receipt.original"),
        ("RETENTION_RECEIPT_ACK.record", "retention-ack.original"),
    ]:
        copy_stream(output / remote_name, local_logs / local_name)
    for row in ctx["external_logs"]:
        remote = Path(row["path"])
        put(remote, b"INVENTED collection terminal log\n", True)
        target = local_logs / (row["label"] + ".log.original")
        copy_stream(remote, target)
        ident = list(tc.ident(remote.lstat()))
        logs.append(
            dict(
                label=row["label"],
                remote_path=row["path"],
                source_identity_before=ident,
                source_identity_after=ident,
                bytes=remote.stat().st_size,
                sha256=pair.digest(remote.read_bytes()),
                local_name=target.name,
            )
        )
    ended = time.time_ns()
    final_terminal = dict(
        version="stage12_terminal_collection_scheduler_v1",
        scope=pair.TEST,
        collection_job_id=0,
        source_git_sha="0" * 40,
        binding_sha256=ctx["binding_sha256"],
        scheduler_state="COMPLETED",
        exit_code="0:0",
        start_epoch_ns=epoch - 1_000_000,
        end_epoch_ns=ended,
        observed_epoch_ns=time.time_ns(),
    )
    index = dict(
        version="stage12_terminal_log_copies_v1",
        context_sha256=pair.digest(tc.canonical(ctx)),
        logs=logs,
        transport_start_epoch_ns=ended,
        transport_complete_epoch_ns=time.time_ns(),
    )
    final = pair.verify_final_logs(
        result,
        pair.digest(tc.canonical(result)),
        final_terminal,
        index,
        local_logs,
        local_logs / "verified.record",
        time.monotonic_ns(),
        time.time_ns(),
        retained_root=local,
    )
    assert final["status"] == "COLLECTION_INTEGRITY_COMPLETE"
    assert final["workload_verification_complete"] is False
    assert final["local_retained_artifacts_freshly_reopened"] is True
    assert final["independent_outcome_review_still_required"] is True


@pytest.mark.parametrize(
    "key",
    [
        "max_collection_jobs",
        "max_collection_seconds",
        "collection_pool_bytes",
        "collection_pool_creations",
        "control_pool_bytes",
        "original_job_id",
    ],
)
def test_authority_rejects_bool_numeric_fields(tmp_path, key):
    binding, authority, _, _ = case(tmp_path / "case")
    authority[key] = True
    with pytest.raises(tc.Stop):
        pair.validate_authority(authority, binding, True)


@pytest.mark.parametrize(
    "change", ["job", "source", "selection", "scope", "state", "stale"]
)
def test_original_workload_binding_rejected_before_children(
    tmp_path, change, monkeypatch
):
    binding, authority, template, terminal = case(tmp_path / "case")
    if change == "job":
        terminal["job_id"] = 1
    elif change == "source":
        terminal["source_git_sha"] = "1" * 40
    elif change == "selection":
        terminal["workload_selection_sha256"] = "1" * 64
    elif change == "scope":
        terminal["scope"] = "PROTECTED"
    elif change == "state":
        terminal["scheduler_state"] = "RUNNING"
    else:
        terminal["observed_epoch_ns"] = 1
    monkeypatch.setattr(
        pair.subprocess,
        "Popen",
        lambda *a, **k: pytest.fail("must not dispatch children"),
    )
    with pytest.raises(tc.Stop):
        pair.run_pair(
            binding,
            authority,
            template,
            terminal,
            Path(binding["output_path"]),
            True,
            tmp_path / "case",
            time.monotonic_ns(),
            time.time_ns(),
        )


def test_late_bound_fifo_identity_and_version_are_exact(tmp_path):
    binding, _, template, _ = case(tmp_path / "case")
    control = pair.Control(time.monotonic_ns(), binding["valid_until_epoch_ns"], 10)
    actual, selected = pair.bind_template(
        template, binding, control, True, tmp_path / "case"
    )
    assert template["inert_fifos"][0]["identity"] is None
    assert actual["inert_fifos"][0]["identity"] == list(
        tc.ident((tmp_path / "case/allocation/supervisor_wait.fifo").lstat())
    )
    assert selected.sha == pair.digest(tc.canonical(actual))


def test_native_practical_caps_are_closed_without_protected_or_public_extension(
    tmp_path,
):
    binding, _, _, _ = case(tmp_path / "case")
    with pytest.raises(tc.Stop):
        pair.validate_binding(
            dict(binding, scope="PROTECTED", state="ISSUED"), False, None
        )
    assert (
        pair.PRACTICAL["seconds"] == 900 and pair.PRACTICAL["wire_bytes"] == 3 * 2**30
    )
    assert (
        pair.PRACTICAL["read_bytes"] == 32 * 2**30
        and pair.PRACTICAL["write_bytes"] == 8 * 2**30
    )


def test_source_hash_mutation_and_deadline_reject(tmp_path):
    binding, _, _, _ = case(tmp_path / "case")
    path = tmp_path / "case/authority.record"
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**9, 10)
    with pytest.raises(tc.Stop):
        pair.source_hash(path, "0" * 64, control)
    late = pair.Control(time.monotonic_ns() - 20 * 10**9, time.time_ns() - 1, 1)
    with pytest.raises(tc.Stop):
        pair.hash_original(path, late, 65536)


def test_control_publication_is_exclusive_and_pending_is_not_ready(tmp_path):
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**9, 10)
    path = tmp_path / "ready.record"
    control.record(path, dict(status="INVENTED"))
    assert path.read_bytes() == tc.canonical(dict(status="INVENTED"))
    assert path.with_name("ready.record.reservation").exists()
    assert not path.with_name("ready.record.pending").exists()
    with pytest.raises(FileExistsError):
        control.record(path, dict(status="OTHER"))


def test_per_role_launch_and_terminal_deadline_boundary():
    pair.require_role_time(dict(deadline_ns=900), 899)
    with pytest.raises(tc.Stop):
        pair.require_role_time(dict(deadline_ns=900), 900)
    with pytest.raises(tc.Stop):
        pair.require_role_time(dict(deadline_ns=900), 901)
    with pytest.raises(tc.Stop):
        pair.require_role_time(dict(deadline_ns=900), True)


def test_selector_cleanup_cannot_replace_primary(tmp_path, monkeypatch):
    binding, authority, template, terminal = case(tmp_path / "case")

    class BadSelector:
        def get_map(self):
            raise OSError(5, "INVENTED sensitive cleanup text")

        def close(self):
            raise OSError(5, "INVENTED second cleanup")

    monkeypatch.setattr(pair.selectors, "DefaultSelector", BadSelector)

    def reject(*args, **kwargs):
        raise tc.Stop("CHILD_EXIT")

    monkeypatch.setattr(pair.subprocess, "Popen", reject)
    with pytest.raises(tc.Stop) as raised:
        pair.run_pair(
            binding,
            authority,
            template,
            terminal,
            Path(binding["output_path"]),
            True,
            tmp_path / "case",
            time.monotonic_ns(),
            time.time_ns(),
        )
    assert raised.value.args == ("CHILD_EXIT",)
    assert raised.value.cleanup_uncertain is True


def test_control_counter_exhaustion_is_prewrite(tmp_path):
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**9, 10)
    control.creations = 128
    with pytest.raises(tc.Stop):
        control.record(tmp_path / "never.record", dict(status="INVENTED"))
    assert not list(tmp_path.iterdir())
    control2 = pair.Control(time.monotonic_ns(), time.time_ns() + 10**9, 10)
    control2.write_bytes = 16 * 2**20
    with pytest.raises(tc.Stop):
        control2.record(tmp_path / "partial.record", dict(status="INVENTED"))
    assert not (tmp_path / "partial.record").exists()


@pytest.mark.parametrize(
    "state,code,sig",
    [
        ("FAILED", 1, 0),
        ("CANCELLED", 0, 15),
        ("COMPLETED", 1, 0),
        ("COMPLETED", 0, 1),
        ("COMPLETED", False, 0),
    ],
)
def test_failed_original_scheduler_cannot_be_rescued_by_content_true(state, code, sig):
    assert (
        pair.original_candidate_eligible(
            dict(scheduler_state=state, exit_code=code, signal=sig), dict(complete=True)
        )
        is False
    )


def test_original_scheduler_raw_binding_is_exact():
    terminal = dict(job_id=12, scheduler_state="FAILED", exit_code=1, signal=0)
    pair.validate_original_scheduler(b"12|FAILED|1:0\n12.batch|FAILED|1:0\n", terminal)
    for raw in [
        b"12|COMPLETED|0:0\n",
        b"13|FAILED|1:0\n",
        b"12|FAILED|1:0\n12|FAILED|1:0\n",
        b"12|FAILED|1:0|EXTRA\n",
    ]:
        with pytest.raises(tc.Stop):
            pair.validate_original_scheduler(raw, terminal)


def test_original_allocation_unicode_uses_actual_producer_bytes(tmp_path):
    binding, _, _, _ = case(tmp_path / "case")
    control = pair.Control(time.monotonic_ns(), binding["valid_until_epoch_ns"], 10)
    producer_sha = pair.digest(
        (ROOT / "scripts/stage12_ra_g1_allocation.py").read_bytes()
    )
    producer = pair.allocation_producer(control, producer_sha)
    original = tc.parse((tmp_path / "case/original-selection.record").read_bytes())
    original["paths"]["tail"] = str(tmp_path / "case/未生成-São-東京")
    raw = producer.canonical(original)
    assert b"\\u" in raw and "東京".encode() not in raw
    path = tmp_path / "case/unicode-original.record"
    put(path, raw, True)
    parsed = pair.load_control_large(path, pair.digest(raw), control, producer_sha)
    assert parsed == original
    assert producer.digest(parsed) == pair.digest(raw)
    with pytest.raises(tc.Stop):
        tc.parse(
            raw
        )  # the terminal-wire UTF8 canonical contract is deliberately different


def retained_component_case(root):
    """Schema-boundary fixture, not a wire/native workload completion claim."""
    root.mkdir(mode=0o700)
    source = root / "source"
    local = root / "local"
    source.mkdir(mode=0o700)
    local.mkdir(mode=0o700)
    started = time.time_ns()
    entered = time.monotonic_ns()
    context = dict(
        version=pair.VERSION,
        status="PAIR_ENTERED_NOT_COMPLETE",
        scope=pair.TEST,
        original_job_id=0,
        collection_job_id=0,
        original_source_git_sha="0" * 40,
        collection_source_git_sha="0" * 40,
        original_workload_selection_sha256="4" * 64,
        collection_uid=os.geteuid(),
        original_scheduler_state="FAILED",
        original_exit_code=1,
        original_signal=0,
        original_scheduler_sha256="5" * 64,
        selection_sha256="1" * 64,
        binding_sha256="2" * 64,
        authority_sha256="3" * 64,
        entry_mono_ns=entered,
        entry_epoch_ns=started,
        overall_deadline_epoch_ns=started + 60 * 10**9,
        parent_deadline_epoch_ns=started + 30 * 10**9,
        external_logs=[dict(label="slurm", path=str(root / "not-a-real-job.log"))],
        native_or_scientific_acceptance=False,
    )
    artifacts = []
    control = pair.Control(entered, started + 30 * 10**9, 30)
    for label in ["archive", "before", "after", "verification"]:
        path = source / (label + ".original")
        put(path, ("INVENTED SCHEMA-ONLY " + label).encode(), True)
        value = pair.hash_original(path, control, 1024)
        artifacts.append(dict(label=label, path=str(path), **value))
        copy_stream(path, local / (label + ".original"))
    ready = dict(
        version=pair.READY_VERSION,
        scope=pair.TEST,
        context=context,
        artifacts=artifacts,
        parent_controls_byte_limit=16 * 2**20,
        local_retention_byte_limit=65536,
        local_receipt_path=str(root / "unused-native-receipt.record"),
        native_or_scientific_acceptance=False,
    )
    ready_sha = pair.digest(tc.canonical(ready))
    receipt = pair.verify_retention(
        ready,
        ready_sha,
        local,
        local / "receipt.record",
        time.monotonic_ns(),
        time.time_ns(),
    )
    ack = dict(
        version=pair.VERSION,
        status="RETENTION_RECEIPT_DURABLY_ACKNOWLEDGED",
        ready_sha256=ready_sha,
        receipt_sha256=pair.digest(tc.canonical(receipt)),
        receipt=receipt,
        original_job_id=0,
        collection_job_id=0,
        acknowledgement_mono_ns=time.monotonic_ns(),
        native_or_scientific_acceptance=False,
    )
    control.record(root / "owned-ack.record", ack)
    assert tc.parse((root / "owned-ack.record").read_bytes())["receipt"] == receipt
    pair.verify_local_retained(ready, receipt, local, control)
    return ready, receipt, local, control


@pytest.mark.parametrize(
    "mutation", ["changed_bytes", "replaced_same_bytes", "missing", "root_replaced"]
)
def test_final_retained_original_changes_after_owned_ack_are_rejected(
    tmp_path, mutation
):
    ready, receipt, local, control = retained_component_case(tmp_path / "case")
    path = local / "archive.original"
    if mutation == "changed_bytes":
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
        try:
            os.write(fd, b"!")
            os.fsync(fd)
        finally:
            os.close(fd)
    elif mutation == "replaced_same_bytes":
        raw = path.read_bytes()
        path.rename(tmp_path / "preserved-old-archive")
        put(path, raw, True)
    elif mutation == "missing":
        path.rename(tmp_path / "preserved-missing-archive")
    else:
        local.rename(tmp_path / "preserved-old-root")
        local.mkdir(mode=0o700)
    with pytest.raises((tc.Stop, OSError)):
        pair.verify_local_retained(ready, receipt, local, control)


def test_role_cleanup_reserve_is_inside_unchanged_deadlines():
    assert pair.role_kill_at(900 * 10**9, 1680 * 10**9) == 895 * 10**9
    assert pair.role_kill_at(1700 * 10**9, 1680 * 10**9) == 1675 * 10**9
    pair.require_role_time(dict(deadline_ns=900 * 10**9), 899 * 10**9)
    with pytest.raises(tc.Stop):
        pair.require_role_time(dict(deadline_ns=900 * 10**9), 900 * 10**9)


def test_native_full_collection_and_independent_review_window_is_not_truncated():
    end = pair.WINDOW_END_NS
    pair.require_full_collection_window(
        dict(valid_until_epoch_ns=end), end - 1920 * 10**9
    )
    with pytest.raises(tc.Stop):
        pair.require_full_collection_window(
            dict(valid_until_epoch_ns=end), end - 1920 * 10**9 + 1
        )
    with pytest.raises(tc.Stop):
        pair.require_full_collection_window(dict(valid_until_epoch_ns=end), True)


def test_reported_zero_destination_space_stops_before_worker_start(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    binding, authority, template, terminal = case(tmp_path / "case")
    actual = os.statvfs(tmp_path)
    values = {
        name: getattr(actual, name)
        for name in [
            "f_bsize",
            "f_frsize",
            "f_blocks",
            "f_bfree",
            "f_bavail",
            "f_files",
            "f_ffree",
            "f_favail",
            "f_flag",
            "f_namemax",
        ]
    }
    values["f_bavail"] = 0
    calls = []

    def observed_zero(fd):
        calls.append(fd)
        return SimpleNamespace(**values)

    monkeypatch.setattr(pair.os, "fstatvfs", observed_zero)
    monkeypatch.setattr(
        pair.subprocess,
        "Popen",
        lambda *a, **k: pytest.fail("zero space must not start workers"),
    )
    with pytest.raises(tc.Stop) as raised:
        pair.run_pair(
            binding,
            authority,
            template,
            terminal,
            Path(binding["output_path"]),
            True,
            tmp_path / "case",
            time.monotonic_ns(),
            time.time_ns(),
        )
    assert raised.value.args == ("OUTPUT",) and len(calls) == 1
    fs = tc.parse(
        (Path(binding["output_path"]) / "FILESYSTEM_OBSERVATION.record").read_bytes()
    )
    assert fs["derived_available_unreserved_bytes"] == 0
    assert fs["capacity_or_native_containment_guarantee"] is False


@pytest.mark.parametrize(
    "change", ["scope", "version", "root", "external_log", "required_log"]
)
def test_original_scope_and_exact_roots_logs_rejected_before_export(tmp_path, change):
    binding, _, template, _ = case(tmp_path / "case")
    control = pair.Control(time.monotonic_ns(), binding["valid_until_epoch_ns"], 10)
    producer = pair.allocation_producer(control, binding["allocation_producer_sha256"])
    original = producer.parse(
        (tmp_path / "case/original-selection.record").read_bytes()
    )
    pair.validate_original_namespace(original, template, binding, producer, True)
    if change == "scope":
        original["scope"] = "DEVELOPMENT_PROTECTED"
    elif change == "version":
        original["version"] = "UNSUPPORTED"
    elif change == "root":
        template["roots"][0]["path"] = str(tmp_path / "unselected")
    elif change == "external_log":
        template["external_files"] = [
            dict(label="unselected", path=str(tmp_path / "unselected.log"))
        ]
    else:
        template["required_logs"] = []
    with pytest.raises(tc.Stop):
        pair.validate_original_namespace(original, template, binding, producer, True)


def test_control_publication_never_overwrites_dangling_symlink(tmp_path):
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**9, 10)
    path = tmp_path / "ready.record"
    path.symlink_to("missing-target")
    with pytest.raises(tc.Stop) as raised:
        control.record(path, dict(status="INVENTED"))
    assert raised.value.args == ("OUTPUT",)
    assert path.is_symlink() and os.readlink(path) == "missing-target"
    assert not (tmp_path / "missing-target").exists()
    assert path.with_name("ready.record.pending").read_bytes() == tc.canonical(
        dict(status="INVENTED")
    )
    assert path.with_name("ready.record.reservation").is_file()

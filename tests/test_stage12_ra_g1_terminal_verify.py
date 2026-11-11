"""Selected boundary tests; invented records establish no native/runtime PASS."""

import importlib.util
import os
from pathlib import Path
import socket
import pytest
from safe_geocoding_pipeline.preprocessing.stages.s12_retrieval_contract import (
    Stage12Error,
)

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "tested_terminal_verify", ROOT / "scripts/stage12_ra_g1_terminal_verify.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_reads_and_restore_with_write_external_denial(tmp_path):
    module = load()
    path = tmp_path / "invented.bin"
    path.write_bytes(b"abcdef")
    original = os.read
    calls = []
    with module.bounded_reads(lambda: None, calls.append) as counts:
        fd = os.open(path, os.O_RDONLY)
        try:
            assert os.read(fd, 2) == b"ab"
            assert os.pread(fd, 2, 2) == b"cd"
            out = bytearray(2)
            assert os.readv(fd, [out]) == 2
            assert out == b"cd"
            with pytest.raises(RuntimeError):
                path.write_bytes(b"changed")
            with pytest.raises((RuntimeError, PermissionError)):
                socket.socket()
        finally:
            os.close(fd)
    assert path.read_bytes() == b"abcdef" and os.read is original
    assert counts["returned_bytes"] == 6 and calls == [2, 2, 2]


def test_read_bound_is_before_native_read_and_no_refund(tmp_path, monkeypatch):
    module = load()
    path = tmp_path / "one"
    path.write_bytes(b"ab")
    monkeypatch.setattr(module, "MAX_READ_BYTES", 1)
    with module.bounded_reads(lambda: None, lambda n: None) as counts:
        fd = os.open(path, os.O_RDONLY)
        try:
            with pytest.raises(RuntimeError):
                os.read(fd, 2)
            assert os.lseek(fd, 0, os.SEEK_CUR) == 0
            assert counts["read_calls"] == 1 and counts["returned_bytes"] == 0
        finally:
            os.close(fd)


def test_expiry_and_callback_uncertainty_keep_primary(tmp_path):
    module = load()
    path = tmp_path / "one"
    path.write_bytes(b"ab")

    def expired():
        raise TimeoutError("INVENTED_NO_SECRET")

    with module.bounded_reads(expired, lambda n: None):
        fd = os.open(path, os.O_RDONLY)
        try:
            with pytest.raises(TimeoutError):
                os.read(fd, 1)
            assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        finally:
            os.close(fd)

    def uncertain(n):
        raise OSError(5, "INVENTED_NOT_RETAINED")

    with module.bounded_reads(lambda: None, uncertain):
        fd = os.open(path, os.O_RDONLY)
        try:
            with pytest.raises(OSError) as caught:
                os.read(fd, 1)
            assert caught.value.errno == 5
        finally:
            os.close(fd)


@pytest.mark.parametrize(
    "scope", ["PUBLIC_SYNTHETIC_ONLY", "DEVELOPMENT_LOCAL_PREPARATION", None]
)
def test_incompatible_workload_scope_rejected_before_paths(scope):
    module = load()
    with pytest.raises(RuntimeError):
        module.verify_original_workload(
            {"scope": scope}, check=lambda: None, charge_read=lambda n: None
        )


def test_real_source_modules_and_missing_originals_are_not_complete(tmp_path):
    module = load()
    out = tmp_path / "original"
    out.mkdir(mode=0o700)
    selected = dict(
        version="stage12_ra_g1_rep_first64_512_allocation_selection_v1",
        scope="REPRESENTATIVE_NO_SERVICE",
        source_sha="a" * 40,
        paths=dict(output=str(out), tail=str(out / "tail.record"), source=str(ROOT)),
    )
    report = module.verify_original_workload(
        selected, check=lambda: None, charge_read=lambda n: None
    )
    assert not report["complete"] and report["status"] == "ORIGINAL_WORKLOAD_INCOMPLETE"
    assert report["original_timed_acceptance_repaired"] is False
    assert report["current_environment_or_old_clock_equivalence_asserted"] is False


def test_verified_code_bytes_cannot_be_replaced_before_execution(tmp_path):
    module = load()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    path = scripts / "invented.py"
    raw = b"sentinel=23\n"
    path.write_bytes(raw)
    import hashlib

    rows = [
        dict(
            path="scripts/invented.py",
            bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    ]
    actual = module._module(tmp_path, "invented", rows, lambda: None, lambda n: None)
    assert actual.sentinel == 23
    path.write_bytes(b"sentinel=99\n")
    with pytest.raises(RuntimeError):
        module._module(tmp_path, "invented", rows, lambda: None, lambda n: None)


@pytest.mark.parametrize("change", [None, "frozen", "deadline"])
def test_actual_tiny_resource_capsule_and_schema_valid_mismatch(tmp_path, change):
    # Invented typed observations only; real phase engine, codec, files, ACK andreaders.
    from test_s12_ra_g1_execution import session
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operations as contract,
    )

    module = load()
    value, _, _ = session(tmp_path)
    value.start()
    try:
        _, records = value.freeze_and_open(
            frozen_data_inventory_sha256="a" * 64,
            actual_opener=lambda: "TEST_ONLY_INVENTED",
        )
        if change == "frozen":
            records["opener_return"]["frozen_data_inventory_sha256"] = "b" * 64
            (value.root / "opener_return.record").write_bytes(
                contract.c.canonical(records["opener_return"])
            )
        if change is None:
            report = module.verify_resource(
                value.root,
                contract.digest(value.binding),
                value.selection,
                1,
                value.deadline,
                io,
                contract,
                lambda: None,
                expected_frozen_sha="a" * 64,
                test_only=True,
            )
            assert report["rows"] >= 2 and report["current_content_revalidated"]
        else:
            with pytest.raises((RuntimeError, Stage12Error)):
                module.verify_resource(
                    value.root,
                    contract.digest(value.binding),
                    value.selection,
                    1,
                    records["monitor_terminal"]["last_ack_ns"]
                    if change == "deadline"
                    else value.deadline,
                    io,
                    contract,
                    lambda: None,
                    expected_frozen_sha="a" * 64,
                    test_only=True,
                )
    finally:
        if not value.completed:
            value.abort()


def test_typed_memoryview_readv_headroom_is_bytes_not_elements(tmp_path, monkeypatch):
    from array import array

    module = load()
    p = tmp_path / "native"
    p.write_bytes(b"12345678")
    monkeypatch.setattr(module, "MAX_READ_BYTES", 4)
    destination = memoryview(array("I", [0, 0]))
    with module.bounded_reads(lambda: None, lambda n: None):
        fd = os.open(p, os.O_RDONLY)
        try:
            with pytest.raises(RuntimeError):
                os.readv(fd, [destination])
            assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        finally:
            os.close(fd)


@pytest.mark.parametrize("change", [None, "missing", "mixed"])
def test_actual_bootstrap_family_required_and_associated(tmp_path, change):
    from test_s12_ra_g1_bootstrap30 import actual_session
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operations as contract,
    )

    module = load()
    value, clock = actual_session(tmp_path)
    value.start()
    try:
        _, records = value.freeze_and_open(
            frozen_data_inventory_sha256="a" * 64, actual_opener=lambda: "TEST_ONLY"
        )
        if change:
            worker = dict(records["worker_validation"])
            if change == "missing":
                worker.pop("bootstrap_evidence_sha256")
            else:
                worker["bootstrap_evidence_sha256"] = "b" * 64
            (value.root / "worker_validation.record").write_bytes(
                contract.c.canonical(worker)
            )
        arguments = (
            value.root,
            contract.digest(value.binding),
            value.selection,
            1,
            value.deadline,
            io,
            contract,
            lambda: None,
        )
        if change:
            with pytest.raises((RuntimeError, Stage12Error)):
                module.verify_resource(*arguments, test_only=True)
        else:
            assert module.verify_resource(*arguments, test_only=True)[
                "current_content_revalidated"
            ]
    finally:
        if not value.completed:
            value.abort()


def test_legacy_later_scope_rejects_mixed_bootstrap_family_before_stream(
    tmp_path, monkeypatch
):
    from test_s12_ra_g1_execution import session
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operations as contract,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_monitor as monitor,
    )

    module = load()
    value, _, _ = session(tmp_path)
    value.start()
    try:
        _, records = value.freeze_and_open(
            frozen_data_inventory_sha256="a" * 64, actual_opener=lambda: "TEST_ONLY"
        )
        closure = dict(records["preopening"])
        closure["schema_version"] = "stage12_resource_closure_bootstrap30_ra_g1_v1"
        closure["bootstrap_evidence_sha256"] = "b" * 64
        monitor.validate(closure)
        opened = dict(
            records["opener_return"], preopening_closure_sha256=contract.digest(closure)
        )
        terminal = dict(
            records["monitor_terminal"], opener_return_sha256=contract.digest(opened)
        )
        for name, row in (
            ("preopening", closure),
            ("opener_return", opened),
            ("monitor_terminal", terminal),
        ):
            (value.root / (name + ".record")).write_bytes(contract.c.canonical(row))

        def forbidden(*args, **kwargs):
            raise AssertionError("FAMILY_MUST_REJECT_BEFORE_STREAM")

        monkeypatch.setattr(monitor, "read_observations", forbidden)
        with pytest.raises((RuntimeError, Stage12Error)):
            module.verify_resource(
                value.root,
                contract.digest(value.binding),
                value.selection,
                1,
                value.deadline,
                io,
                contract,
                lambda: None,
                test_only=True,
            )
    finally:
        if not value.completed:
            value.abort()


def invented_qualification():
    """Complete invented control originals for pure gate tests; never live authority."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as win
    import stage12_ra_g1_terminal_parent as pair
    import stage12_ra_g1_terminal_verify as verify
    import stat
    canon = verify._q_digest
    start=win.epoch_ns(win.WINDOW_START)
    window=dict(version=win.WINDOW_VERSION,scope="TERMINAL_COLLECTION_NO_SERVICE",valid_from=win.WINDOW_START,
                valid_until=win.WINDOW_END,policy_sha256=win.digest(win.descriptor()),owner_authority_sha256="2"*64,grant_nonce="3"*64)
    domain=dict(host="invented-host",boot_id="11111111-1111-1111-1111-111111111111",mount_namespace="mnt:[11]",session_nonce="4"*32,session_pid=11)
    directory=[1,2,stat.S_IFDIR|0o700,1,1,2,0,1,1]
    file=[1,3,stat.S_IFREG|0o600,1,1,1,8,1,1]
    selection=dict(limits=pair.PRACTICAL)
    selection_sha=canon(selection)
    ctx=dict(version=pair.SUCCESSOR_VERSION,status="PAIR_ENTERED_NOT_COMPLETE",scope=pair.NATIVE,original_job_id=1812987,collection_job_id=1900001,
             original_source_git_sha=win.ORIGINAL_SOURCE,collection_source_git_sha="b"*40,
             original_workload_selection_sha256=win.ORIGINAL_SELECTION,collection_uid=1,original_scheduler_state="FAILED",
             original_exit_code=1,original_signal=0,original_scheduler_sha256="a"*64,selection_sha256=selection_sha,
             binding_sha256="b"*64,authority_sha256="c"*64,entry_mono_ns=1,entry_epoch_ns=start+1,
             overall_deadline_epoch_ns=start+1800*10**9,parent_deadline_epoch_ns=start+1680*10**9,
             external_logs=[dict(label="stdout",path="/invented/log")],native_or_scientific_acceptance=False,
             window=window,collection_purpose="QUALIFICATION",original_source_root="/invented-source",
             original_producer_path="/invented-source/scripts/stage12_ra_g1_allocation.py",original_producer_sha256="d"*64)
    artifacts=[dict(label=label,path="/invented/"+label,bytes=8,sha256=("e" if label=="archive" else "f")*64,identity=list(file))
               for label in ("archive","before","after","verification")]
    ready=dict(version=pair.SUCCESSOR_READY_VERSION,scope=pair.NATIVE,context=ctx,artifacts=artifacts,collection_selection=selection,
               parent_controls_byte_limit=16*2**20,local_retention_byte_limit=32,local_receipt_path="/invented/RETENTION_RECEIPT.record",native_or_scientific_acceptance=False)
    def evidence(rows):
        return dict(version="stage12_same_session_transfer_v2",domain_before=domain,domain_after=domain,
                    ancestors=[dict(path=path,before=list(directory),after=list(directory)) for path in ("/","/invented")],
                    files=[dict(label=r["label"],path=r["path"],before=list(file),after=list(file),bytes=r["bytes"],sha256=r["sha256"]) for r in rows],
                    exit_code=0,observed_joined=True)
    def opener(at):
        return dict(version="stage12_readonly_collection_archive_open_v1",status="COMPLETE",selection_sha256=selection_sha,
                    archive_sha256="e"*64,summary=dict(members=1,payload_bytes=8,manifest_bytes=8,manifest_sha256="f"*64),
                    actual_read_bytes=64,actual_read_calls=8,entered_epoch_ns=at,completed_epoch_ns=at+1,
                    source_identity=list(file),native_or_scientific_acceptance=False)
    receipt=dict(version=pair.SUCCESSOR_RECEIPT_VERSION,scope=pair.NATIVE,ready_sha256=canon(ready),original_job_id=1812987,
                 collection_job_id=ctx["collection_job_id"],selection_sha256=selection_sha,artifacts=[],local_root="/retained",
                 local_root_identity=directory[:5],local_start_epoch_ns=start+2,local_complete_epoch_ns=start+101,
                 actual_read_bytes=100,actual_read_calls=10,native_or_scientific_acceptance=False,
                 transport_evidence=evidence(artifacts),whole_collection_opener=opener(start+90))
    ack=dict(version=pair.SUCCESSOR_VERSION,status="RETENTION_RECEIPT_DURABLY_ACKNOWLEDGED",ready_sha256=canon(ready),receipt_sha256=canon(receipt),
             receipt=receipt,original_job_id=1812987,collection_job_id=ctx["collection_job_id"],acknowledgement_mono_ns=3,native_or_scientific_acceptance=False)
    provisional=dict(version=pair.SUCCESSOR_VERSION,status="PROVISIONAL_INTEGRITY_COMPLETE_PENDING_TERMINAL_LOGS_AND_REVIEW",context=ctx,
                     children_joined=True,exits=dict(receive=0,export=0),local_transport_and_hash_receipt_verified=True,
                     candidate_native_eligible=False,ready_sha256=canon(ready),receipt_sha256=canon(receipt),receipt_ack_sha256=canon(ack))
    terminal=dict(version="stage12_terminal_collection_scheduler_v1",scope=pair.NATIVE,collection_job_id=ctx["collection_job_id"],
                  source_git_sha=ctx["collection_source_git_sha"],binding_sha256=ctx["binding_sha256"],scheduler_state="COMPLETED",exit_code="0:0",
                  start_epoch_ns=start,end_epoch_ns=start+1000,observed_epoch_ns=start+1001)
    log=dict(label="stdout",remote_path="/invented/log",source_identity_before=list(file),source_identity_after=list(file),bytes=8,sha256="e"*64,local_name="stdout.log.original")
    index=dict(version="stage12_terminal_same_domain_log_copies_v2",context_sha256=canon(ctx),logs=[log],
               transport_start_epoch_ns=start+1002,transport_complete_epoch_ns=start+1003,
               transport_evidence=evidence([dict(label="stdout",path="/invented/log",bytes=8,sha256="e"*64)]))
    post=opener(start+1004)
    final=dict(version=pair.SUCCESSOR_FINAL_VERSION,status="COLLECTION_INTEGRITY_COMPLETE",local_retained_artifacts_freshly_reopened=True,
               candidate_native_eligible=False,provisional_sha256=canon(provisional),terminal_sha256=canon(terminal),log_index_sha256=canon(index),
               original_workload_selection_sha256=win.ORIGINAL_SELECTION,original_job_id=1812987,collection_job_id=ctx["collection_job_id"],
               native_or_scientific_acceptance=False,whole_collection_opener=post,observed_complete_epoch_ns=start+1006)
    transport=dict(version="stage12_terminal_same_domain_bounded_transport_v2",status="LOCAL_STREAMS_HASHED_AWAITING_NATIVE_ACK",
                   ready_sha256=canon(ready),receipt_sha256=canon(receipt),original_job_id=1812987,collection_job_id=ctx["collection_job_id"],
                   native_or_scientific_acceptance=False,transport_evidence=receipt["transport_evidence"])
    bundle=dict(version=verify.QUALIFICATION_VERSION,window=window,final=final,provisional=provisional,ready=ready,receipt=receipt,ack=ack,
                terminal=terminal,index=index,transport=transport,opener=post)
    review=dict(version="stage12_terminal_collection_qualification_review_v1",scope=window["scope"],status="PASS",
                collection_job_id=ctx["collection_job_id"],collection_source_git_sha=ctx["collection_source_git_sha"],original_job_id=1812987,
                original_source_git_sha=win.ORIGINAL_SOURCE,original_selection_sha256=win.ORIGINAL_SELECTION,
                final_sha256=canon(final),ready_sha256=canon(ready),receipt_ack_sha256=canon(ack),terminal_sha256=canon(terminal),
                index_sha256=canon(index),transport_sha256=canon(transport),opener_sha256=canon(post),reviewed_epoch_ns=start+1007,
                reviewer_role="INDEPENDENT_COLLECTION_QUALIFICATION",independent_review=True)
    bundle["review"]=review
    kwargs=dict(expected_window=window,expected_original_source_git_sha=win.ORIGINAL_SOURCE,expected_original_job_id=1812987,
                expected_original_selection_sha256=win.ORIGINAL_SELECTION,expected_collector_source_git_sha=ctx["collection_source_git_sha"],
                expected_qualification_review_sha256=canon(review))
    return bundle,kwargs


def test_invented_collection_qualification_exact_bindings():
    import stage12_ra_g1_terminal_verify as verify
    bundle,kwargs=invented_qualification()
    assert verify.validate_qualification(bundle,**kwargs) is bundle


@pytest.mark.parametrize("part,key,value", [
    ("ready","version","stage12_terminal_transport_ready_v1"),
    ("terminal","exit_code","1:0"),
    ("provisional","children_joined",False),
    ("ack","status","MISSING"),
    ("review","independent_review",False),
    ("opener","status","INCOMPLETE"),
])
def test_invented_collection_qualification_fails_closed(part,key,value):
    import copy
    import stage12_ra_g1_terminal_verify as verify
    bundle,kwargs=invented_qualification()
    bundle=copy.deepcopy(bundle)
    bundle[part][key]=value
    with pytest.raises((RuntimeError,KeyError)):
        verify.validate_qualification(bundle,**kwargs)

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

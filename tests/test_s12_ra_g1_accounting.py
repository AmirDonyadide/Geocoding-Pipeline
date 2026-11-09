"""Compiler arithmetic/reader tests; invented inventories never issue authority."""

from copy import deepcopy
import hashlib
from pathlib import Path
import stat
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as monitor
from test_s12_ra_g1_core import H, selection, observation, original_observation


def inputs(size=9):
    sources = [dict(path="src/SYNTHETIC_ONLY.py", bytes=size, sha256=H)]
    backends = [
        dict(
            ordinal=i,
            module=name,
            path="/SYNTHETIC_PREPARATION_NOT_EXECUTABLE/" + name + ".so",
            identity=dict(
                device=2**63 + i,
                inode=i,
                mode=stat.S_IFREG | 0o500,
                uid=123,
                gid=123,
                nlink=1,
                bytes=i,
                mtime_ns=1,
                ctime_ns=1,
            ),
            stat_scope="PREPARATION_HOST_SNAPSHOT",
            sha256=H,
        )
        for i, name in enumerate(a.MODULES, 1)
    ]
    return sources, backends


@pytest.mark.parametrize(
    "scope,rows,scans,stages,source_passes,backend_passes",
    [
        ("REPRESENTATIVE_NO_SERVICE", 3948, 9582, 9, 12, 6),
        ("PUBLIC_SYNTHETIC_ONLY", 16066, 32132, 14, 16, 13),
    ],
)
def test_closed_derived_graph_stage_totals_and_original_scan_counts(
    scope, rows, scans, stages, source_passes, backend_passes
):
    sources, backends = inputs()
    inventory, accounting = a.compile_inventory(sources, backends, scope)
    assert a.validate_inventory(inventory) == inventory
    assert set(inventory) == set(a.descriptor()["outer_fields"])
    assert inventory["execution_permission"] == "NOT_ISSUED"
    assert (
        inventory["backend_identity_scope"] == "PREPARATION_ONLY_NOT_COMPUTE_IDENTITY"
    )
    assert inventory["proof_count"]["actual_monitor_rows"] == rows
    assert inventory["proof_count"]["fresh_monitor_row_validations"] == scans
    assert inventory["proof_count"]["full_source_sweeps"] == source_passes
    assert inventory["proof_count"]["full_backend_sweeps"] == backend_passes
    assert len(inventory["stage_accounting"]) == stages
    assert accounting == {
        key: sum(row[key] for row in inventory["stage_accounting"])
        for key in a.ACCOUNTING_KEYS
    }
    assert a.stage_accounting(inventory, 1) != a.stage_accounting(inventory, stages)
    for row in inventory["cost_rows"]:
        assert set(row) == set(a.descriptor()["cost_row_fields"])
        assert (
            row["original_read_calls"]
            == row["invocations"] * row["per_invocation_read_calls"]
        )
        assert (
            row["original_read_bytes"]
            == row["invocations"] * row["per_invocation_read_bytes"]
        )
    assert all(0 < value <= a.MAX_U for value in accounting.values())


def test_exact_source_byte_limits_missing_backend_unknown_graph_and_mutations():
    sources, backends = inputs(a.SOURCE_MAX)
    inventory, _ = a.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")
    sources[0]["bytes"] += 1
    with pytest.raises(a.AccountingError):
        a.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")
    sources, _ = inputs()
    with pytest.raises(a.AccountingError, match="BACKENDS_UNAVAILABLE"):
        a.compile_inventory(sources, [], "PUBLIC_SYNTHETIC_ONLY")
    for key in ("accounting", "cost_rows", "stage_accounting", "proof_count"):
        changed = deepcopy(inventory)
        if key == "accounting":
            changed[key]["check_calls"] += 1
        elif key == "cost_rows":
            changed[key][0]["original_read_bytes"] += 1
        elif key == "stage_accounting":
            changed[key][0]["original_read_calls"] += 1
        else:
            changed[key]["source_files"] += 1
        with pytest.raises(a.AccountingError, match="CHANGED"):
            a.validate_inventory(changed)
    protected, caps = a.compile_inventory(sources, backends, "DEVELOPMENT_ONLY")
    assert caps is None and protected["accounting"] is None
    assert protected["stage_accounting"] == [] and protected["cost_rows"] == []
    with pytest.raises(a.AccountingError, match="UNISSUED"):
        a.stage_accounting(protected, 1)


def test_source_or_backend_size_changes_force_new_inventory_and_no_host_identity_claim():
    sources, backends = inputs()
    before, _ = a.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")
    sources[0]["bytes"] += 1
    after, _ = a.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")
    assert before["accounting"] != after["accounting"] and a.digest(before) != a.digest(
        after
    )
    backends[0]["identity"]["inode"] += 1
    host_only, _ = a.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")
    assert host_only["accounting"] == after["accounting"]
    assert host_only["backend_inventory_sha256"] != after["backend_inventory_sha256"]
    backends[0]["identity"]["bytes"] += 1
    resized, _ = a.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")
    assert resized["accounting"] != host_only["accounting"]
    broken = deepcopy(backends)
    broken[0]["identity"]["bytes"] = a.MAX_U
    with pytest.raises(a.AccountingError, match="OVERFLOW"):
        a.compile_inventory(sources, broken, "PUBLIC_SYNTHETIC_ONLY")


def test_one_byte_short_read_eof_and_failure_bytes_charge_actuals(
    tmp_path, monkeypatch
):
    path = tmp_path / "SYNTHETIC_ONLY"
    path.write_bytes(b"abc")
    import os

    original = os.read
    monkeypatch.setattr(monitor.os, "read", lambda fd, size: original(fd, min(size, 1)))
    charges = []
    fd = os.open(path, os.O_RDONLY)
    try:
        observed = b""
        while True:
            raw = monitor.charged_read(
                fd, 4096, lambda calls, size: charges.append((calls, size))
            )
            if not raw:
                break
            observed += raw
    finally:
        os.close(fd)
    assert (
        observed == b"abc"
        and sum(c for c, n in charges) == 4
        and sum(n for c, n in charges) == 3
    )
    bound = a.stream_bound(3)
    assert bound == dict(read_calls=4, read_bytes=4)
    assert charges[-2:] == [(1, 0), (0, 0)]


def test_monitor_writer_real_original_and_codec_readbacks_are_charged(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    originals = root / "originals"
    originals.mkdir(mode=0o700)
    row = observation(selection())
    raw = monitor.export_original_observation(
        original_observation(row), allow_synthetic=True
    )
    calls = []
    end = time.monotonic_ns() + 5 * 10**9
    writer = monitor.ObservationWriter(
        root / "observations.bin",
        maximum_rows=2,
        charge=lambda *args: None,
        check=lambda: None,
        original_root=originals,
        charge_read=lambda c, n: calls.append((c, n)),
    )
    identity = writer.stage_original(raw)
    row["visible_identity_inventory_sha256"] = identity
    block = monitor.pack_observation(row)
    writer.append(block, 1, end)
    writer.wait(1, end)
    writer.close(end)
    assert sum(c for c, n in calls) == (len(raw) + 4095) // 4096 + 1
    assert sum(n for c, n in calls) == len(raw) + 1024
    assert (
        hashlib.sha256((originals / (identity + ".record")).read_bytes()).hexdigest()
        == identity
    )


def test_descriptor_asset_matches_exact_export():
    root = Path(__file__).resolve().parents[1]
    assert (
        root / "docs/scientific_assets" / (a.VERSION + ".json")
    ).read_bytes() == a.canonical(a.descriptor())


def test_representative_stage_costs_match_actual_preparer_attempts_writes_and_creation_guards():
    """Counterexample: phase2 is160attempts, not55; phase3 is40, not20."""
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "SYNTHETIC_ONLY_actual_b_preparer", root / "scripts/stage12_prepare_ra_g1.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    sources, backends = inputs()
    inventory, accounting = a.compile_inventory(
        sources, backends, "REPRESENTATIVE_NO_SERVICE"
    )
    allocation = dict(
        valid_from="2026-01-01T00:00:00.000000Z",
        valid_until="2026-01-02T00:00:00.000000Z",
        source_sha="2" * 40,
        source_files=sources,
        accounting=accounting,
        accounting_inventory=inventory,
    )
    selected = builder.resource_selection(
        allocation,
        policy_sha256=H,
        adoption_sha256=H,
        descriptor_inventory_sha256=H,
        graph_sha256=H,
        paths_sha256=H,
        implementation_review_sha256=H,
    )
    expected = [5 * phase[3] for phase in builder.PHASES]
    assert expected == [320, 160, 40, 15]
    for stage, q in zip(selected["limits"]["stages"][:4], expected, strict=True):
        own = {
            row["component"]: row
            for row in inventory["cost_rows"]
            if row["stage_id"] == stage["id"]
        }
        assert stage["attempts"] == q
        assert (
            own["APPLICATION_BYTE_SHORT_WRITE_GUARDS"]["per_invocation_checks"]
            == stage["logical_write_bytes"]
        )
        assert own["PREWRITE_ORIGINAL_RESOURCE_BINDINGS"]["invocations"] == 7 * (
            stage["creations"] + q
        )
        assert {
            key: stage[key]
            for key in ("source_read_calls", "source_read_bytes", "check_calls")
        } == a.stage_accounting(inventory, stage["id"])
    control = [
        row
        for row in inventory["cost_rows"]
        if row["component"] == "AUTHORITY_RUNTIME_START_DISPATCH_RECORDS"
    ]
    assert "FIVE_B_OR_SIX_PUBLIC" in control[0]["basis"]


def test_source_parent_guards_follow_exact_depth_even_for_empty_files(
    tmp_path, monkeypatch
):
    """RC01: before/after source-parent checks add4*depth+files per sweep."""
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_public as public

    shallow, backends = inputs(size=0)
    shallow[0]["path"] = "empty.py"
    deep = [{**shallow[0], "path": "one/two/three/empty.py"}]
    root = tmp_path / "SYNTHETIC_ONLY_source"
    (root / "one/two/three").mkdir(mode=0o700, parents=True)
    calls = dict(deadline=0, predicate=0)

    def checkpoint():
        calls["deadline"] += 1

    original_require = public.o.require

    def predicate(condition, reason=None):
        calls["predicate"] += 1
        return (
            original_require(condition)
            if reason is None
            else original_require(condition, reason)
        )

    monkeypatch.setattr(public.o, "require", predicate)
    owner = SimpleNamespace(
        repository=root,
        _deadline_check=checkpoint,
        _stat_identity=public.Authority._stat_identity,
    )
    relative = Path(deep[0]["path"])
    first = public.Authority._source_parent_identities(owner, relative)
    second = public.Authority._source_parent_identities(owner, relative)
    predicate(first == second)
    actual_parent_guards = calls["deadline"] + calls["predicate"]
    assert actual_parent_guards == 4 * 3 + 1
    for scope in ("REPRESENTATIVE_NO_SERVICE", "PUBLIC_SYNTHETIC_ONLY"):
        leaf, leaf_caps = a.compile_inventory(shallow, backends, scope)
        nested, nested_caps = a.compile_inventory(deep, backends, scope)
        assert leaf["proof_count"]["source_internal_parent_entries"] == 0
        assert leaf["proof_count"]["source_parent_guard_checks_per_full_sweep"] == 1
        assert nested["proof_count"]["source_internal_parent_entries"] == 3
        assert (
            nested["proof_count"]["source_parent_guard_checks_per_full_sweep"]
            == actual_parent_guards
        )
        own = next(
            row
            for row in nested["cost_rows"]
            if row["component"] == "EXACT_FULL_SOURCE_SWEEPS"
        )
        assert own["per_invocation_checks"] == 3 * (0 + 1) + 6 + actual_parent_guards
        assert nested_caps["original_read_calls"] == leaf_caps["original_read_calls"]
        assert nested_caps["original_read_bytes"] == leaf_caps["original_read_bytes"]
        assert (
            nested_caps["check_calls"] - leaf_caps["check_calls"]
            == 12 * nested["proof_count"]["full_source_sweeps"]
        )
        assert set(nested["proof_count"]) == set(a.descriptor()["proof_count_fields"])

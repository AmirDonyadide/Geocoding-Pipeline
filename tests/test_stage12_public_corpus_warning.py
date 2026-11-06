"""Finite corpus warning policy; invented bytes and offline denial guards only."""

from copy import deepcopy
from pathlib import Path
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_response as v
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_corpus_policy as policy,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operational_audit as oa,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operations as operations,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as legacy
from test_stage12_public_operations_v2 import (
    H,
    KEY,
    FakeClock,
    inputs,
    rebind,
    offline,  # noqa: F401 -- autouse denial fixture
)
from test_stage12_public_operational_audit import capture
from test_stage12_public_matrix import configuration
from test_stage12_public_runtime import config_test_only


def work(entry):
    return {
        "work_id": 1,
        "block_id": 1,
        "kind": "DATA",
        "fixture_id": entry["fixture_id"],
        "result_limit": entry["result_limit"],
        "repetition": 0,
        "recipe_id": None,
        "retry_spacing_key": entry["fixture_id"],
    }


def sample(entry, *, features=False):
    obj = {
        "type": "FeatureCollection",
        "features": [],
        "geocoding": {
            "warnings": [v.WARNING],
            "query": {
                "text": entry["text"],
                "size": entry["result_limit"],
                "boundary.country": entry["country_echo"],
                "layers": ["locality", "street"],
                "lang": {"name": "Test language"},
            },
        },
    }
    if features:
        obj["features"] = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 2]},
                "properties": {
                    "source": "synthetic",
                    "layer": "locality",
                    "accuracy": "centroid",
                },
            }
        ]
    return obj


def sao(size=1):
    return next(
        x
        for x in policy.allowlist()
        if x["text"] == "São Paulo" and x["result_limit"] == size
    )


def test_size40_public_validation_has_cooperative_boundaries_without_policy_change():
    entry = sao(40)
    row = work(entry)
    obj = sample(entry, features=True)
    obj["features"] *= 40
    raw = c.canonical(obj)
    expected = tuple(
        response.structural(x)
        for x in response.Parser(raw).parse().value["features"]
    )
    calls = []
    with io.cooperative_io(lambda: calls.append(True)):
        actual = v.shapes(raw, row, version=v.CORPUS_VERSION)
        limitation = v.Validation(v.CORPUS_VERSION).limitation(raw, row)
    assert actual == expected
    assert limitation["raw_sha256"] == c.sha(raw).hex()
    assert len(calls) >= 80  # Both validation and structural work yield by feature.
    assert c.sha(c.canonical(v.descriptor(v.CORPUS_VERSION))).hex() == (
        "849a0863876b75dcef322a46d74c2558708cb8611046c8235869090cce621ae2"
    )


def test_public_validation_safe_point_failure_cannot_become_valid():
    entry = sao(40)
    raw = c.canonical(sample(entry, features=True))

    def uncertain_writer():
        raise OSError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")

    with io.cooperative_io(uncertain_writer):
        with pytest.raises(OSError):
            v.shapes(raw, work(entry), version=v.CORPUS_VERSION)


def test_exact_descriptor_and_original_versions_preserved():
    for version in v.VERSIONS:
        assert (
            c.canonical(v.descriptor(version))
            == (Path("docs/scientific_assets") / (version + ".json")).read_bytes()
        )
    d = v.descriptor(v.CORPUS_VERSION)
    assert d["request_allowlist_count"] == 144
    assert d["request_allowlist_sha256"] == c.sha(c.canonical(policy.allowlist())).hex()
    assert d["fixture_inventory_sha256"] == c.sha(c.canonical(probe.fixtures())).hex()
    assert (
        d["approved_matrix_manifest_sha256"]
        == "c3776bc1b7f85df948bf1cb3e293c7ff67562c26ac0108260e8fd0d03ecc00fe"
    )
    planned = {
        (row["fixture_id"], row["result_limit"], v.target(row))
        for index in range(10)
        for row in matrix.work_for(index, H)[0]
        if next(f for f in probe.fixtures() if f["fixture_id"] == row["fixture_id"])[
            "core"
        ]["search_mode"]
        == "FULL_TEXT"
    }
    assert planned == {
        (x["fixture_id"], x["result_limit"], x["target_ascii"].encode())
        for x in policy.allowlist()
    }
    assert len(planned) == 144


@pytest.mark.parametrize(
    "entry",
    policy.allowlist(),
    ids=lambda x: x["fixture_id"][:8] + "_" + str(x["result_limit"]),
)
def test_every_frozen_target_has_exact_echo_and_reduced_coverage(entry):
    row = work(entry)
    raw = c.canonical(sample(entry, features=True))
    result = v.shapes(raw, row, version=v.CORPUS_VERSION)
    assert len(result) == 1
    side = v.Validation(v.CORPUS_VERSION).limitation(raw, row)
    assert side["exception_applied"]
    assert side["eligible_request_target_sha256"] == c.sha(v.target(row)).hex()
    assert (
        side["coverage_limitation"] == "ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED"
    )
    assert side["scientific_publication_authorized"] is False
    assert side["continuous_service_state"] == "NOT_VERIFIED"
    assert side["raw_sha256"] == c.sha(raw).hex()
    # Structural output retains the actual source/layer/accuracy; no point-quality label.
    assert result == tuple(
        response.structural(x) for x in response.Parser(raw).parse().value["features"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "unplanned_size",
        "deep_unselected",
        "structured",
        "control",
        "unknown_fixture",
        "text_case",
        "text_trim",
        "wrong_country",
        "alpha2_country",
        "multiple_countries",
        "missing_country",
        "wrong_size",
        "float_size",
        "exponent_size",
        "bool_size",
        "string_size",
        "warning_duplicate",
        "warning_extra",
        "warning_unknown",
        "warning_top",
        "warning_string",
        "error_top",
        "error_geo",
        "missing_query",
        "missing_text",
        "missing_size",
        "empty_layers",
        "duplicate_layers",
        "address_layer",
        "returned_address",
        "returned_unknown_layer",
        "empty_lang",
        "bad_geometry",
        "too_many_features",
        "malformed",
    ],
)
def test_corpus_near_misses_fail(mutation):
    entry = sao(3)
    row = work(entry)
    obj = sample(entry, features=True)
    geo, q = obj["geocoding"], obj["geocoding"]["query"]
    if mutation == "unplanned_size":
        row["result_limit"] = q["size"] = 2
    if mutation == "deep_unselected":
        entry = next(x for x in policy.allowlist() if "\n" in x["text"])
        row = work(entry)
        row["result_limit"] = 20
        obj = sample(entry)
        geo = obj["geocoding"]
        q = geo["query"]
        q["size"] = 20
    if mutation == "structured":
        row["fixture_id"] = next(
            f["fixture_id"]
            for f in probe.fixtures()
            if f["core"]["search_mode"] == "STRUCTURED"
        )
    if mutation == "control":
        row["kind"] = "SERVICE_CONTROL"
    if mutation == "unknown_fixture":
        row["fixture_id"] = "0" * 64
    if mutation == "text_case":
        q["text"] = q["text"].lower()
    if mutation == "text_trim":
        q["text"] += " "
    if mutation == "wrong_country":
        q["boundary.country"] = ["DEU"]
    if mutation == "alpha2_country":
        q["boundary.country"] = ["BR"]
    if mutation == "multiple_countries":
        q["boundary.country"] += ["DEU"]
    if mutation == "missing_country":
        del q["boundary.country"]
    if mutation == "wrong_size":
        q["size"] = 1
    if mutation == "bool_size":
        q["size"] = True
    if mutation == "string_size":
        q["size"] = "3"
    if mutation == "warning_duplicate":
        geo["warnings"] *= 2
    if mutation == "warning_extra":
        geo["warnings"].append("other")
    if mutation == "warning_unknown":
        geo["warnings"] = ["unknown"]
    if mutation == "warning_top":
        obj["warnings"] = geo.pop("warnings")
    if mutation == "warning_string":
        geo["warnings"] = v.WARNING
    if mutation == "error_top":
        obj["errors"] = ["synthetic"]
    if mutation == "error_geo":
        geo["errors"] = ["synthetic"]
    if mutation == "missing_query":
        del geo["query"]
    if mutation == "missing_text":
        del q["text"]
    if mutation == "missing_size":
        del q["size"]
    if mutation == "empty_layers":
        q["layers"] = []
    if mutation == "duplicate_layers":
        q["layers"] *= 2
    if mutation == "address_layer":
        q["layers"].append("address")
    if mutation == "returned_address":
        obj["features"][0]["properties"]["layer"] = "address"
    if mutation == "returned_unknown_layer":
        obj["features"][0]["properties"]["layer"] = "country"
    if mutation == "empty_lang":
        q["lang"] = {}
    if mutation == "bad_geometry":
        obj["features"][0]["geometry"]["coordinates"][0] = 181
    if mutation == "too_many_features":
        obj["features"] *= 4
    raw = c.canonical(obj)
    if mutation == "float_size":
        raw = raw.replace(b'"size":3', b'"size":3.0')
    if mutation == "exponent_size":
        raw = raw.replace(b'"size":3', b'"size":3e0')
    if mutation == "malformed":
        raw = b"{"
    with pytest.raises(c.Stage12Error):
        v.shapes(raw, row, version=v.CORPUS_VERSION)


def test_exact_newline_echo_is_not_silently_sanitized():
    entry = next(x for x in policy.allowlist() if "\n" in x["text"])
    obj = sample(entry)
    obj["geocoding"]["query"]["text"] = entry["text"].replace("\n", "")
    with pytest.raises(c.Stage12Error):
        v.shapes(c.canonical(obj), work(entry), version=v.CORPUS_VERSION)


@pytest.mark.parametrize("mutation", ["fixture_membership", "target", "mode", "path"])
def test_actual_materialization_and_frozen_fixture_manifest_are_required(
    monkeypatch, mutation
):
    entry = sao()
    row = work(entry)
    if mutation == "target":
        monkeypatch.setattr(
            v,
            "target",
            lambda work: b"/v1/search?boundary.country=DE&size=1&text=Berlin",
        )
    else:
        fs = deepcopy(probe.fixtures())
        if mutation == "fixture_membership":
            fs.append(deepcopy(fs[0]))
        else:
            f = next(f for f in fs if f["fixture_id"] == row["fixture_id"])
            f["core"]["search_mode" if mutation == "mode" else "endpoint"] = (
                "STRUCTURED" if mutation == "mode" else "/v1/autocomplete"
            )
        monkeypatch.setattr(probe, "fixtures", lambda: fs)
    with pytest.raises(c.Stage12Error):
        v.shapes(c.canonical(sample(entry)), row, version=v.CORPUS_VERSION)


def test_no_control_or_old_validator_or_scientific_helper_acquires_new_exception():
    row = work(sao())
    raw = c.canonical(sample(sao()))
    for version in (v.VERSION, v.FAMILY_VERSION):
        with pytest.raises(c.Stage12Error):
            v.shapes(raw, row, version=version)
    with pytest.raises(c.Stage12Error):
        v.ordinary_shapes(raw, 1)
    with pytest.raises(c.Stage12Error):
        legacy.public_shapes(raw)
    # All supplemental adapter recipes retain the unchanged ordinary validator.
    for recipe in matrix.recipes(H):
        with pytest.raises(c.Stage12Error):
            matrix.CheckAdapter(recipe).validate(recipe, raw)


@pytest.mark.parametrize("version", [v.VERSION, v.FAMILY_VERSION])
def test_old_warning_free_invalid_fixture_rejection_is_preserved(version):
    row = work(sao())
    row["fixture_id"] = "0" * 64
    obj = sample(sao())
    del obj["geocoding"]["warnings"]
    with pytest.raises(c.Stage12Error):
        v.shapes(c.canonical(obj), row, version=version)


def test_new_validator_is_opt_in_matrix_only_and_old_matrix_remains_valid():
    cfg = configuration()
    runtime.validate_config(cfg)
    cfg["public_validation_sha256"] = operations.digest(v.descriptor(v.CORPUS_VERSION))
    runtime.validate_config(cfg)
    assert (
        runtime.validation_for(cfg["public_validation_sha256"]).VERSION
        == v.CORPUS_VERSION
    )
    old = config_test_only()
    old["public_validation_sha256"] = cfg["public_validation_sha256"]
    with pytest.raises(c.Stage12Error):
        runtime.validate_config(old)


@pytest.mark.parametrize("country", ["DE", "FR", "JP", "GR", "EG", "IN", "KR", "BR"])
def test_capture_and_actual_reopen_preserve_exact_raw_and_country_binding(
    tmp_path, country
):
    entry = next(
        x
        for x in policy.allowlist()
        if x["boundary_country"] == country and x["result_limit"] == 40
    )
    row = work(entry)
    p, plan, start, rows, inventory = inputs(1)
    rows[:] = [row]
    rebind(p, plan, start, rows)
    adapter = v.Validation(v.CORPUS_VERSION)
    root = tmp_path / "attempt"
    oa.begin_data(root, p, plan, start, row, 1, inventory, validation=adapter)
    raw = c.canonical(sample(entry, features=True))
    transport = oa.transport_record(row, 1, capture(raw), FakeClock().utc())
    terminal, _ = oa.finish_data(
        root,
        row,
        transport,
        raw,
        key=KEY,
        validator=adapter.validator(row, root),
        validation=adapter,
    )
    assert (
        terminal["outcome"] == "SUCCESS_WITH_CANDIDATES"
        and terminal["validation_version"] == v.CORPUS_VERSION
    )
    assert (
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=adapter.validator(row, root),
            context=oa.DataContext(adapter),
        )
        == terminal
    )
    assert (
        io.metadata(io.read(root / "public_limitation.json"))["raw_sha256"]
        == c.sha(raw).hex()
    )
    with pytest.raises(c.Stage12Error):
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=v.Validation(v.FAMILY_VERSION).validator(row, root),
            context=oa.DataContext(v.Validation(v.FAMILY_VERSION)),
        )


def test_secret_echo_is_never_captured_even_for_eligible_warning(tmp_path):
    entry = sao()
    row = work(entry)
    p, plan, start, rows, inventory = inputs(1)
    rows[:] = [row]
    rebind(p, plan, start, rows)
    adapter = v.Validation(v.CORPUS_VERSION)
    root = tmp_path / "attempt"
    oa.begin_data(root, p, plan, start, row, 1, inventory, validation=adapter)
    obj = sample(entry)
    obj["injected_secret"] = KEY.decode()
    raw = c.canonical(obj)
    terminal, _ = oa.finish_data(
        root,
        row,
        oa.transport_record(row, 1, capture(raw), FakeClock().utc()),
        raw,
        key=KEY,
        validator=adapter.validator(row, root),
        validation=adapter,
    )
    assert terminal["reason_code"] == "SECRET_ECHO_DETECTED"
    for path in root.iterdir():
        assert (
            KEY not in path.read_bytes()
            and c.sha(raw).hex().encode() not in path.read_bytes()
        )
    assert (
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=adapter.validator(row, root),
            context=oa.DataContext(adapter),
        )
        == terminal
    )


@pytest.mark.parametrize(
    "field",
    [
        "approved_matrix_manifest_sha256",
        "fixture_inventory_sha256",
        "request_allowlist_sha256",
        "eligible_request_target_sha256",
        "version",
    ],
)
def test_limitation_static_bindings_reject_tampering_without_valid_payload(
    tmp_path, field
):
    row = work(sao())
    adapter = v.Validation(v.CORPUS_VERSION)
    side = adapter.limitation(None, row)
    side[field] = "0" * 64
    io.reserve(tmp_path / "attempt")
    io.write(tmp_path / "attempt" / "public_limitation.json", c.canonical(side))
    with pytest.raises(c.Stage12Error):
        adapter.verify_limitation(tmp_path / "attempt", row, {})


@pytest.mark.parametrize(
    "field",
    [
        "approved_matrix_manifest_sha256",
        "fixture_inventory_sha256",
        "request_allowlist_sha256",
        "eligible_request_target_sha256",
        "version",
    ],
)
def test_successful_payload_limitation_bindings_are_recomputed(tmp_path, field):
    entry = sao()
    row = work(entry)
    raw = c.canonical(sample(entry))
    adapter = v.Validation(v.CORPUS_VERSION)
    root = tmp_path / "attempt"
    io.reserve(root)
    side = adapter.limitation(raw, row)
    side[field] = "0" * 64
    io.write(root / "public_limitation.json", c.canonical(side))
    with pytest.raises(c.Stage12Error):
        adapter.validator(row, root)(raw)


def test_corpus_policy_actual_coordinator_publication_and_full_reopening(tmp_path):
    from test_stage12_public_scheduler import repair_common
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j

    p, plan, start, rows, inventory = inputs(4, 20)
    p["states"][0].update(connections=1, admitted_operations=1)
    selected = [
        next(
            x
            for x in policy.allowlist()
            if x["boundary_country"] == country and x["result_limit"] == 3
        )
        for country in ["BR", "JP"]
    ]
    for row, entry in zip(rows, [x for x in selected for _ in range(2)]):
        row.update(
            fixture_id=entry["fixture_id"],
            retry_spacing_key=entry["fixture_id"],
            result_limit=entry["result_limit"],
            repetition=(row["work_id"] - 1) % 2,
        )
    rebind(p, plan, start, rows)
    clock = FakeClock()
    dispatched = []

    def dispatch(row, target, hooks):
        entry = policy.entry(row["fixture_id"], row["result_limit"])
        assert target == entry["target_ascii"].encode()
        dispatched.append(row["work_id"])
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        value = capture(c.canonical(sample(entry, features=True)))
        hooks.completed(value)
        return value

    root = tmp_path / "complete"
    result = legacy.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        dispatch=dispatch,
        epoch=H,
        public_validation=v.Validation(v.CORPUS_VERSION),
        **repair_common(rows, inventory),
    )
    assert dispatched == [1, 2, 3, 4]
    assert result["disposition"] == "COMPLETED"
    assert result["campaign_counts"]["durable_valid_data"]["value"] == 4
    comparisons = list(j.read_array(root / "repeat_comparison.json"))
    assert len(comparisons) == 2 and all(x["equal"] for x in comparisons)
    reopened = runtime.reopen_completed(
        root,
        p,
        plan,
        start,
        validation_sha256=operations.digest(v.descriptor(v.CORPUS_VERSION)),
    )
    assert reopened["counts"]["durable_valid_data"]["value"] == 4
    assert (root / "_SEGMENT_SEALED").exists()
    assert (root / "_WRITER_RELEASED.json").exists()

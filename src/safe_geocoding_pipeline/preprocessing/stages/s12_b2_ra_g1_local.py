"""LP-1 local-only successor; never permission to contact or publish a service.

Authority is an explicitly provisioned exact registry grant, not an inference
from an evidence hash. Original accepted readers and scientific algorithms are
reused. This module creates no institution/operator attestations.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from copy import deepcopy
from . import s12_b2_local_preparation as strict
from . import s12_b2_contract as b
from . import s12_b2_calibration as calibration
from . import s12_b2_operations as operations
from . import s12_b2_work_assembly as assembly
from . import s12_storage as io

RUNTIME_VERSION = "stage12_development_runtime_lp1_ra_g1_v1"
DESCRIPTOR = "stage12_local_preparation_authority_b2_ra_g1_v1"
ASSET = deepcopy(strict.ASSET)
ASSET["descriptor_version"] = DESCRIPTOR
ASSET["parent_descriptor_sha256"] = strict.DESCRIPTOR_SHA256
ASSET["normative_schema_sha256"] = (
    "193c6b749af1981e20b829a6d25d07103966e0bbffeb07c5e38ed895f5a32e25"
)
ASSET["runtime_version"] = RUNTIME_VERSION
ASSET["authority_schema"]["schema_version"] = "=" + DESCRIPTOR
ASSET["current_schema"]["schema_version"] = (
    "=stage12_local_preparation_current_b2_ra_g1_v1"
)
for key in (
    "phase_memory_bytes",
    "phase_disk_capacity_bytes",
    "phase_generation_bound_bytes",
):
    ASSET["authority_schema"]["bounds"].pop(key, None)
ASSET["authority_schema"]["bounds"].update(
    phase_monitor_selection_sha256="D",
    phase_capacity_observation_sha256="D",
    phase_logical_write_ceiling_bytes="P",
)
ASSET["authority_schema"]["resource_assurance_binding_sha256"] = "D"
ASSET["resource_assurance"] = "LOGICAL_LIMITS_AND_SCOPED_MONITORING"
ASSET["native_maximum"] = "NOT_PROVEN"
ASSET["physical_maximum"] = "NOT_PROVEN"
DESCRIPTOR_SHA256 = b.digest(ASSET)
_raw = (
    Path(__file__).resolve().parents[4]
    / "docs/scientific_assets"
    / (DESCRIPTOR + ".json")
).read_bytes()
b.require(_raw == b.canonical(ASSET), "LP1_RA_DESCRIPTOR_CHANGED")
PHASES = ASSET["phases"]
EXTRA_FIELDS = frozenset(
    ("local_preparation_authority_sha256", "local_preparation_current_path")
)
SERVICE_FIELDS = frozenset(
    (
        "permission_sha256",
        "permission_current_path",
        "gate",
        "window_state_path",
        "response_rules_sha256",
        "campaign",
        "transport",
        "postflight_bundle_path",
    )
)
REFERENCES = (
    "local_source_use_sha256",
    "local_controller_scope_sha256",
    "controlled_location_scope_sha256",
    "owner_offline_preparation_sha256",
    "scientific_decision_sha256",
    "implementation_review_sha256",
    "denial_policy_sha256",
    "revocation_source_sha256",
)
BOUNDS = tuple(ASSET["authority_schema"]["bounds"])


def scope_hash(config):
    value = deepcopy(config)
    for key in ("authority_sha256", "local_preparation_authority_sha256"):
        value["runtime"].pop(key, None)
    if value["runtime"].get("resource_retention") is not None:
        value["runtime"]["resource_retention"].pop("slot_binding_sha256", None)
    return b.digest(value)


def workload_parameters_hash(config):
    return b.digest(
        {
            k: v
            for k, v in config.items()
            if k not in {"runtime", "local_workload_sha256"}
        }
    )


def accepted_manifest_hashes():
    from . import s10_query_input as accepted
    from . import s12_b2_catalog as catalogs

    return {
        "stage06": accepted.STAGE06_MANIFEST,
        "stage08": accepted.accepted8.STAGE08_MANIFEST_SHA256,
        "stage09": accepted.STAGE09_MANIFEST,
        "stage11": catalogs.ACCEPTED["manifest_sha256"],
    }


def validate_config(config):
    from . import s12_b2_ra_g1_contract as contract

    contract.validate_configuration(config)
    r = config["runtime"]
    b.require(
        r["version"] == RUNTIME_VERSION
        and r["mode"] == "OFFLINE_ONLY"
        and r["phase"] in PHASES
        and all(r[k] is None for k in SERVICE_FIELDS),
        "LP1_LOCAL_ONLY",
    )
    b.validate_type(r["local_preparation_authority_sha256"], "D")
    b.require(type(r["local_preparation_current_path"]) is str, "LP1_LOCAL_ONLY")
    b.validate_type(config["local_workload_sha256"], "D")
    b.require(type(config["local_accepted_roots"]) is dict, "LP1_INPUT_BINDING")
    if "local_dispatch_layouts" in config:
        layouts = config["local_dispatch_layouts"]
        b.require(
            r["phase"] == "build-workload"
            and type(layouts) is list
            and 1 <= len(layouts) <= 10,
            "LP1_DISPATCH_LAYOUT",
        )
        for index, layout in enumerate(layouts, 1):
            assembly.validate_layout(layout)
            b.require(layout["intent_ordinal"] == index, "LP1_DISPATCH_LAYOUT")


def required_source_paths():
    """Closed static internal import graph for every LP-1 entry point.

    The graph is derived by the already hash-bound LP-1 validator and every
    discovered byte is then required in the separately supplied source
    inventory. Conservative optional branches are included; omission cannot
    silently narrow the reviewed executable identity.
    """
    import ast

    repository = Path(__file__).resolve().parents[4]
    package = repository / "src/safe_geocoding_pipeline"
    queue = [
        repository
        / "src/safe_geocoding_pipeline/preprocessing/stage12_development_cli.py",
        repository
        / "src/safe_geocoding_pipeline/preprocessing/stages/s12_b2_runtime.py",
        Path(__file__).resolve(),
    ]
    seen = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        b.require(
            path.is_file() and path.is_relative_to(package),
            "LP1_EXECUTABLE_BINDING",
        )
        seen.add(path)
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            base = path.parent
            for _ in range(node.level - 1):
                base = base.parent
            if node.module:
                module = base.joinpath(*node.module.split("."))
                candidate = module.with_suffix(".py")
                if candidate.is_file() and candidate.is_relative_to(package):
                    queue.append(candidate)
                for alias in node.names:
                    candidate = module / (alias.name + ".py")
                    if candidate.is_file() and candidate.is_relative_to(package):
                        queue.append(candidate)
            else:
                for alias in node.names:
                    candidate = base / (alias.name + ".py")
                    if candidate.is_file() and candidate.is_relative_to(package):
                        queue.append(candidate)
    for directory in {path.parent for path in seen}:
        while directory.is_relative_to(package):
            init = directory / "__init__.py"
            if init.is_file():
                seen.add(init)
            if directory == package:
                break
            directory = directory.parent
    paths = {str(path.relative_to(repository)) for path in seen}
    paths |= {
        "docs/scientific_assets/" + DESCRIPTOR + ".json",
        "docs/scientific_assets/stage12_resource_acceptance_graph_descriptor_b2_ra_g1_v1.json",
        "docs/scientific_assets/stage12_allocation_limits_descriptor_b2_ra_g1_v1.json",
        "docs/scientific_assets/stage12_resource_retention_descriptor_b2_rs1_v1.json",
        "docs/scientific_assets/stage12_allocation_limits_descriptor_b2_rs1_v1.json",
    }
    return frozenset(paths)


def validate_source_closure(source_files):
    paths = [x["path"] for x in source_files]
    b.require(
        len(paths) == len(set(paths)) and required_source_paths() <= set(paths),
        "LP1_EXECUTABLE_BINDING",
    )


class Gate:
    """Exact local authority and real denial must precede original input access."""

    def __init__(self, port):
        self.port, self.records, self.authority = port, port.records, port.authority
        self.scope = port.population_scope
        self.local_only = True

    def check(self):
        p, r, config = self.port, self.port.settings, self.port.config
        p.check_deadline()
        validate_config(config)
        b.require(
            p.offline_guard is not None
            and not p.offline_guard.closed
            and p._key is None,
            "LP1_DENIAL_NOT_ACTIVE",
        )
        # Denial remains active in every thread; no provider is instantiated.
        p.offline_guard.assert_active()
        p._source_check()
        h = r["local_preparation_authority_sha256"]
        a = io.metadata(self.records.raw(h))
        b.validate_type(a, ASSET["authority_schema"])
        b.require(
            a["population_scope"] == self.scope
            and a["configuration_scope_sha256"] == scope_hash(config)
            and a["source_inventory_sha256"] == b.digest(r["source_files"])
            and a["stage11_input_binding_sha256"] == config["input_binding_sha256"]
            and a["workload_sha256"] == config["local_workload_sha256"]
            and a["accepted_roots"] == config["local_accepted_roots"]
            and a["phase"] == PHASES[p.phase]
            and a["output_parent"] == r["output_parent"]
            and a["scratch_parent"] == r["scratch_parent"]
            and a["bounds"] == {k: r[k] for k in BOUNDS}
            and a["valid_from"] <= p.clock.utc() <= p.phase_until < a["valid_until"],
            "LP1_AUTHORITY_SCOPE",
        )
        b.require(
            getattr(p, "ra_binding_sha256", None)
            == a["resource_assurance_binding_sha256"]
            and type(getattr(p, "ra_binding", None)) is dict
            and p.ra_binding["scope"] == "DEVELOPMENT_LOCAL_PREPARATION",
            "LP1_RA_ASSURANCE_BINDING",
        )
        for name in REFERENCES:
            self.records.raw(a[name])
        b.require(
            a["scientific_decision_sha256"] == r["scientific_decision_sha256"]
            and io.metadata(self.records.raw(a["denial_policy_sha256"]))
            == ASSET["denial_policy"],
            "LP1_AUTHORITY_SCOPE",
        )
        self.authority.require("local_preparation", h, a)
        current = io.metadata(io.read(Path(r["local_preparation_current_path"])))
        b.validate_type(current, ASSET["current_schema"])
        b.require(
            current["authority_sha256"] == h
            and current["state"] == "CURRENT"
            and current["valid_from"]
            <= p.clock.utc()
            <= p.phase_until
            < current["valid_until"],
            "LP1_REVOKED_OR_EXPIRED",
        )
        self.records.raw(current["evidence_sha256"])
        self.authority.require("local_preparation_current", b.digest(current), current)
        decision = self.records.get(
            r["scientific_decision_sha256"], "scientific_decision"
        )
        b.require(
            decision["decision"] == "ADOPT_CONDITIONAL"
            and decision["amendment_sha256"] == b.AMENDMENT_SHA256
            and decision["schema_spec_sha256"] == b.SPEC_SHA256,
            "B2_SCIENCE_UNADOPTED",
        )
        self.authority.require("scientific_decision", b.digest(decision), decision)
        for k in ("accepted_limitations_sha256", "owner_delegation_sha256"):
            self.records.raw(decision[k])
        binding = self.records.get(
            config["input_binding_sha256"], "stage11_input_binding"
        )
        b.require(binding["population_scope"] == self.scope, "LP1_INPUT_BINDING")
        for stage, item in a["accepted_roots"].items():
            path = Path(item["path"])
            b.require(
                path.is_absolute()
                and ".." not in path.parts
                and str(path) == config.get(stage + "_root"),
                "LP1_INPUT_BINDING",
            )
        b.require(
            a["accepted_roots"]["stage11"]["manifest_sha256"]
            == binding["manifest_sha256"],
            "LP1_INPUT_BINDING",
        )
        if self.scope == b.DEVELOPMENT:
            b.require(
                {k: v["manifest_sha256"] for k, v in a["accepted_roots"].items()}
                == accepted_manifest_hashes(),
                "LP1_INPUT_BINDING",
            )
            source_root = Path(r["source_root"])
            b.require(
                source_root == Path(__file__).resolve().parents[4],
                "LP1_EXECUTABLE_BINDING",
            )
            validate_source_closure(r["source_files"])
        workload = io.metadata(self.records.raw(config["local_workload_sha256"]))
        b.validate_type(workload, ASSET["workload_schema"])
        b.require(
            workload["phase"] == PHASES[p.phase]
            and workload["input_binding_sha256"] == config["input_binding_sha256"]
            and workload["parameters_sha256"] == workload_parameters_hash(config),
            "LP1_WORKLOAD_SCOPE",
        )
        if p.output is not None:
            b.require(
                workload["output_path"] == str(p.output)
                and workload["scratch_path"] == str(p.scratch),
                "LP1_WORKLOAD_SCOPE",
            )
        io.private_directory(Path(r["output_parent"]))
        io.private_directory(Path(r["scratch_parent"]))
        return a

    def require(self, purpose, digest, context):
        b.require(
            purpose
            in {
                "local_preparation",
                "scientific_decision",
                "protected_input",
                "protected_lineage_input",
                "witness_interpretation",
                "lineage_projection",
                "calibration_depths",
                "supported_size",
                "administrative_writer",
                "nonsecret_record",
            },
            "LP1_SERVICE_AUTHORITY_DENIED",
        )
        self.check()
        self.authority.require(purpose, digest, context)

    def before_dispatch(self, *args, **kwargs):
        b.require(False, "LP1_SERVICE_AUTHORITY_DENIED")

    admit = emitted = validate_campaign = segment_closure = before_dispatch


def local_authority_check(port, purpose, digest, context):
    """Deny service uses even if a forged registry includes such a grant.

    Derived contexts are authorized only while the reviewed original projection
    iterator yields that exact row. No campaign-sized permission/cache exists.
    """
    if purpose == "lineage_context":
        port.check_deadline()
        b.require(
            port.phase == "build-catalog"
            and port._local_context is not None
            and port._local_context == (digest, b.digest(context)),
            "LP1_LINEAGE_SCOPE",
        )
        return True
    allowed = {
        "local_preparation",
        "local_preparation_current",
        "scientific_decision",
        "resources",
        "protected_input",
        "protected_lineage_input",
        "witness_interpretation",
        "lineage_projection",
        "calibration_depths",
        "supported_size",
        "administrative_writer",
        "nonsecret_record",
        "resource_retention",
        "resource_retention_review",
        "resource_retention_retry_state_proof",
        "resource_retention_resource_assurance_selection",
        "resource_retention_initial_capacity_observation",
        "resource_retention_native_risk_inventory",
        "resource_retention_native_role_inventory",
        "resource_retention_adoption",
        "resource_retention_allocation_ceiling",
        "resource_graph_binding",
        "resource_graph_begin",
        "resource_graph_prerequisite_local_authority",
        "resource_registered_paths",
        "resource_phase_terminal",
        "resource_setup_counter_prefix",
        "resource_policy",
        "resource_adoption",
        "resource_selection",
        "resource_technical_review",
        "resource_invocation_graph",
        "resource_risk_inventory",
        "owner_reported_project_approval",
        "resource_retention_filesystem_accounting",
        "resource_retention_codec_inventory",
        "resource_retention_encoding_inventory",
        "resource_retention_bound",
        "resource_retention_allocation_limits",
    }
    b.require(
        purpose in allowed or purpose == "phase_" + port.phase,
        "LP1_SERVICE_AUTHORITY_DENIED",
    )
    return False


@contextmanager
def lineage_scope(port, projection):
    """Bound one producer row at a time, without storing its protected content."""
    original = projection.rows

    def rows():
        for row in original():
            metadata = {**row, "channels": []}
            port._local_context = (row["origin_sha256"], b.digest(metadata))
            try:
                yield row
            finally:
                port._local_context = None

    port.gate.check()
    projection.rows = rows
    try:
        yield
    finally:
        projection.rows = original
        port._local_context = None
        port.gate.check()


def core_selection(port, catalog, scratch):
    """Recompute full retained selection before generating any unbound workload."""
    h = port.config["calibration_plan_sha256"]
    core = port.records.get(h, "calibration_plan")
    b.require(
        core["population_scope"] == catalog.binding["population_scope"]
        and core["stage11_input_binding_sha256"] == b.digest(catalog.binding),
        "LP1_SELECTION_BINDING",
    )
    selected = calibration.select(
        catalog,
        scratch,
        C=core["C"],
        T=core["T"],
        supported=port.authority.supported_size(core["capability_evidence_sha256"]),
        authority=port.authority,
        decision_hash=core["decision_sha256"],
    )
    b.require(
        selected["grid"] == core["grid"]
        and b.digest(selected["tail"]) == core["tail_inventory_sha256"]
        and b.digest(selected["paired"]) == core["paired_inventory_sha256"]
        and b.digest(selected["coverage"]) == core["coverage_sha256"],
        "LP1_SELECTION_BINDING",
    )
    full = operations.manifest_digest(
        row["query_semantic_id"].hex() for row in catalog.semantics()
    )
    expected = [
        {
            "schema_version": "stage12_calibration_work_intent_b2_v1",
            "workload_kind": x["kind"],
            "result_limit": x["size"],
            "repetition": x["repetition"],
            "subset_inventory_sha256": full
            if x["subset"] is None
            else core["tail_inventory_sha256"]
            if x["kind"] == "TAIL"
            else core["paired_inventory_sha256"],
            "planned_data": x["count"],
        }
        for x in selected["intents"]
    ]
    b.require(
        b.canonical(expected) == port.records.raw(core["workload_inventory_sha256"]),
        "LP1_SELECTION_BINDING",
    )
    return core, selected


def execute_metadata(phase, session, resources, catalog_for):
    """No window, admission, transmission or scientific publication is produced."""
    p, config = session.port, session.configuration
    p.gate.check()
    base = {
        "schema_version": "stage12_local_preparation_result_b2_ra_g1_v1",
        "phase": PHASES[phase],
        "local_authority_sha256": p.settings["local_preparation_authority_sha256"],
        "configuration_sha256": b.digest(config),
        "input_binding_sha256": config["input_binding_sha256"],
        "service_transfer_authority": "NOT_GRANTED",
        "scientific_publication": "NOT_GRANTED",
    }
    if phase == "prepare-bootstrap":
        result = {
            **base,
            "source_inventory_sha256": b.digest(p.settings["source_files"]),
            "denial_policy_sha256": b.digest(ASSET["denial_policy"]),
        }
        io.write(session.output, b.canonical(result))
        return result
    catalog = catalog_for(session, resources)
    catalog.verify()
    core, selected = core_selection(p, catalog, session.scratch)
    # All rows are derived again from the exact catalog. Each scientific intent
    # remains distinct. This local file carries no service campaign/observation ID.
    b.require(not session.output.exists(), "LP1_OUTPUT_EXISTS")
    io.reserve(session.output)
    inventories = []
    work_files = []
    layouts = config.get("local_dispatch_layouts")
    if layouts is not None:
        b.require(len(layouts) == len(selected["intents"]), "LP1_DISPATCH_BINDING")
    for index, intent in enumerate(selected["intents"], 1):
        p.check_deadline()
        name = f"intent_{index:02}.jsonl"
        count = 0
        import hashlib
        import os

        h = hashlib.sha256()
        from . import s12_b2_allocation_limits as limits

        limits.claim("PREFIX_FILE")
        fd = os.open(
            session.output / name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                expected = (
                    (row["query_semantic_id"].hex() for row in catalog.semantics())
                    if intent["subset"] is None
                    else iter(sorted(intent["subset"]))
                )
                for count, q in enumerate(expected, 1):
                    p.check_deadline()
                    raw = b.canonical(
                        {
                            "ordinal": count,
                            "query_semantic_id": q,
                            "result_limit": intent["size"],
                            "repetition": intent["repetition"],
                            "workload_kind": intent["kind"],
                        }
                    )
                    io.charge_write(session.output / name, len(raw))
                    stream.write(raw)
                    h.update(raw)
                stream.flush()
                os.fsync(stream.fileno())
            b.require(count == intent["count"], "LP1_WORK_TOTALITY")
        except BaseException:
            # The exact partial file is retained and never accepted as a result.
            raise
        inventories.append({"name": name, "rows": count, "sha256": h.hexdigest()})
        if layouts is not None:
            p.gate.check()
            work_files.append(
                assembly.assemble(
                    session.output / name,
                    session.output / f"work_{index:02}.jsonl",
                    inventories[-1],
                    intent,
                    layouts[index - 1],
                    check=p.check_deadline,
                )
            )
            p.gate.check()
    catalog.verify()
    p.gate.check()
    result = {
        **base,
        "calibration_plan_sha256": b.digest(core),
        "inventories": inventories,
        "ready_for_service": False,
        "depths_independently_authorized": True,
    }
    if layouts is not None:
        for item, intent, layout, receipt in zip(
            inventories, selected["intents"], layouts, work_files, strict=True
        ):
            assembly.reopen(
                session.output / receipt["name"],
                item,
                intent,
                layout,
                receipt,
                check=p.check_deadline,
            )
        result["dispatch_work_files"] = work_files
    io.write(session.output / "local_result.json", b.canonical(result))
    # Fresh read of original generated files after write; no cached evidence token.
    for item in inventories:
        h = hashlib.sha256()
        with (session.output / item["name"]).open("rb") as stream:
            while chunk := stream.read(65536):
                p.check_deadline()
                h.update(chunk)
        b.require(h.hexdigest() == item["sha256"], "LP1_OUTPUT_CHANGED")
    return result


# Exact compatibility: the accepted process-wide provider/audit denials are
# shared, so strict and RA local scopes cannot install conflicting wrappers.
Denial = strict.Denial


def reopen_metadata(port, config, output, result, scratch, catalog_factory):
    """Fresh original LP1 output/selection/WorkFile validation, with denials live."""
    import hashlib
    import os
    from itertools import zip_longest

    port.gate.check()
    if port.phase == "prepare-bootstrap":
        b.require(
            io.metadata(io.read(output)) == result
            and result["service_transfer_authority"]
            == result["scientific_publication"]
            == "NOT_GRANTED"
            and result["source_inventory_sha256"]
            == b.digest(port.settings["source_files"]),
            "LP1_RA_OPENER_BINDING",
        )
        port.gate.check()
        return result
    b.require(
        io.metadata(io.read(output / "local_result.json")) == result,
        "LP1_RA_OPENER_BINDING",
    )
    catalog = catalog_factory()
    catalog.verify()
    core, selected = core_selection(port, catalog, scratch)
    b.require(
        result["calibration_plan_sha256"] == b.digest(core)
        and len(result["inventories"]) == len(selected["intents"]),
        "LP1_RA_OPENER_BINDING",
    )
    expected_names = {"local_result.json"}
    layouts = config.get("local_dispatch_layouts")
    receipts = result.get("dispatch_work_files")
    b.require(
        (layouts is None) == (receipts is None)
        and (receipts is None or len(receipts) == len(selected["intents"])),
        "LP1_DISPATCH_BINDING",
    )
    for index, (item, intent) in enumerate(
        zip(result["inventories"], selected["intents"], strict=True), 1
    ):
        b.require(
            set(item) == {"name", "rows", "sha256"}
            and item["name"] == f"intent_{index:02}.jsonl"
            and item["rows"] == intent["count"],
            "LP1_RA_OPENER_BINDING",
        )
        expected_names.add(item["name"])
        path = output / item["name"]
        before = path.stat(follow_symlinks=False)
        h = hashlib.sha256()
        expected = (
            (row["query_semantic_id"].hex() for row in catalog.semantics())
            if intent["subset"] is None
            else iter(sorted(intent["subset"]))
        )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        count = 0
        with os.fdopen(fd, "rb") as stream:

            def rows():
                while True:
                    port.check_deadline()
                    port.charge_ra_original_read(1, 4097)
                    raw = stream.readline(4097)
                    if not raw:
                        return
                    b.require(len(raw) <= 4096, "LP1_RA_OUTPUT_ROW_BOUND")
                    h.update(raw)
                    yield io.metadata(raw)

            for count, (row, q) in enumerate(zip_longest(rows(), expected), 1):
                b.require(
                    row is not None
                    and q is not None
                    and row
                    == {
                        "ordinal": count,
                        "query_semantic_id": q,
                        "result_limit": intent["size"],
                        "repetition": intent["repetition"],
                        "workload_kind": intent["kind"],
                    },
                    "LP1_WORK_TOTALITY",
                )
            after = os.fstat(stream.fileno())

        def identity(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_uid,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        b.require(
            count == intent["count"]
            and h.hexdigest() == item["sha256"]
            and identity(before)
            == identity(after)
            == identity(path.stat(follow_symlinks=False)),
            "LP1_OUTPUT_CHANGED",
        )
        if receipts is not None:
            receipt = receipts[index - 1]
            b.require(
                receipt["name"] == f"work_{index:02}.jsonl", "LP1_DISPATCH_BINDING"
            )
            expected_names.add(receipt["name"])
            assembly.reopen(
                output / receipt["name"],
                item,
                intent,
                layouts[index - 1],
                receipt,
                check=port.check_deadline,
            )
    b.require(
        {path.name for path in output.iterdir()} == expected_names, "LP1_OUTPUT_CHANGED"
    )
    catalog.verify()
    port.gate.check()
    return result

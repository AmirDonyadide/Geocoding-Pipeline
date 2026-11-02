"""B2-RS1 closed physical allocation model and conservative command ledger.

This is accounting, not capacity creation. Proof records and attributable
capacity require actual independent authority. Unknown live bounds never parse.
Old O1 records and its scalar reservation retain their existing semantics.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from . import s12_b2_contract as b
from . import s12_storage as io

DESCRIPTOR = "stage12_resource_retention_descriptor_b2_rs1_v1"
DESCRIPTOR_SHA256 = "05e5e8ed01baec323b0f64e31b40e91f05c4663e408b294e3bfe7db85a9f42c0"
_raw = (
    Path(__file__).resolve().parents[4]
    / "docs/scientific_assets"
    / (DESCRIPTOR + ".json")
).read_bytes()
b.require(b.sha(_raw).hex() == DESCRIPTOR_SHA256, "B2_RS1_DESCRIPTOR_CHANGED")
ASSET = json.loads(_raw)
MODEL, PROFILE, PLAN = (ASSET[x] for x in ("model", "profile", "plan"))
COUNTS = ASSET["count_sources"]
MODEL_SCHEMA = ASSET["model_schema"]
MAX_COMMANDS = ASSET["max_commands"]
COMMAND_PHASES = tuple(ASSET["command_phases"])
MANDATORY_COMMAND_PHASES = frozenset(ASSET["mandatory_command_phases"])
RUNTIME_BINDING_SCHEMA = ASSET["runtime_binding_schema"]


def shape(value, schema):
    if isinstance(schema, list):
        b.require(
            type(value) is list and len(value) <= MAX_COMMANDS, "B2_RS1_LIST_BOUND"
        )
        for item in value:
            shape(item, schema[0])
    elif isinstance(schema, dict) and not any(
        k in schema for k in ("enum", "const", "primitive", "tag")
    ):
        b.require(type(value) is dict and set(value) == set(schema), "B2_RS1_FIELDS")
        for k, child in schema.items():
            shape(value[k], child)
    else:
        b.validate_type(value, schema)


def add(*values):
    return b.uint(sum(b.uint(x) for x in values))


def mul(a, z):
    return b.uint(b.uint(a) * b.uint(z))


def component_bytes(component, model):
    """Conservative separate-file rounding; no compression or sparse credit."""
    count, size, inodes = (
        component[x]
        for x in (
            "count_bound",
            "per_instance_bytes_bound",
            "per_instance_inodes_bound",
        )
    )
    b.require(not count or (size > 0 and inodes > 0), "B2_RS1_INODE_BOUND")
    block = model["block_bytes"]
    # Even an empty allowed allocation receives one block per possible inode.
    per = add(
        mul((add(size, block - 1) // block), block),
        mul(inodes, block),
        mul(inodes, model["inode_overhead_bytes"]),
    )
    return mul(count, per), mul(count, inodes), mul(count, size)


def validate_model(model):
    shape(model, MODEL_SCHEMA)
    b.require(
        model["adopted_clauses_sha256"] == ASSET["adopted_source_sha256"],
        "B2_RS1_ADOPTION",
    )
    b.require(model["valid_from"] < model["valid_until"], "B2_RS1_VALIDITY")
    limits = model["limits"]
    b.require(
        limits["max_response_bytes"] == 16 * 2**20
        and 1 <= limits["max_candidates_per_work"] <= 40,
        "B2_RS1_RESPONSE_BOUND",
    )
    for prefix in ("data", "control"):
        works, attempts = limits[prefix + "_works"], limits[prefix + "_attempts"]
        b.require(works <= attempts <= mul(5, works), "B2_RS1_RETRY_BOUND")
    b.require(
        limits["candidate_rows"]
        <= mul(limits["data_works"], limits["max_candidates_per_work"]),
        "B2_RS1_CANDIDATE_BOUND",
    )
    members = model["member_workloads"]
    b.require(
        0 < len(members) <= MAX_COMMANDS
        and [x["plan_binding_sha256"] for x in members]
        == sorted({x["plan_binding_sha256"] for x in members})
        and model["workload_sha256"] == aggregate_workload_hash(model),
        "B2_RS1_AGGREGATE_WORKLOAD",
    )
    b.require(
        limits["max_candidates_per_work"] == max(x["result_limit"] for x in members)
        and all(
            x["candidate_rows"] == mul(x["data_works"], x["result_limit"])
            for x in members
        ),
        "B2_RS1_CANDIDATE_BOUND",
    )
    for name in (
        "data_works",
        "data_attempts",
        "control_works",
        "control_attempts",
        "candidate_rows",
        "events",
        "ledger_rows",
    ):
        b.require(
            limits[name] == sum(x[name] for x in members),
            "B2_RS1_AGGREGATE_WORKLOAD",
        )
    commands = model["commands"]
    b.require(
        0 < len(commands) <= MAX_COMMANDS and limits["commands"] == len(commands),
        "B2_RS1_COMMAND_BOUND",
    )
    b.require(
        [x["command_id"] for x in commands] == list(range(1, len(commands) + 1)),
        "B2_RS1_COMMAND_ORDER",
    )
    phases = [x["phase"] for x in commands]
    b.require(
        MANDATORY_COMMAND_PHASES <= set(phases)
        and all(x in COMMAND_PHASES for x in phases),
        "B2_RS1_COMMAND_GRAPH",
    )
    components = model["components"]
    b.require(
        [x["component_id"] for x in components] == sorted(COUNTS),
        "B2_RS1_CATEGORY_COVERAGE",
    )
    physical = inodes = retained = 0
    for component in components:
        kind = component["component_id"]
        b.require(
            component["count_bound"] == limits[COUNTS[kind]], "B2_RS1_COUNT_DERIVATION"
        )
        predicate = (
            "TERMINAL_BODY_ONCE"
            if kind in ("DATA_RAW", "CONTROL_RAW")
            else "EVERY_ATTEMPT"
            if kind
            in (
                "DATA_ATTEMPT_METADATA",
                "CONTROL_ATTEMPT_METADATA",
                "CONTROL_VERIFICATION",
            )
            else "TRANSIENT_NO_RECLAIM"
            if kind
            in (
                "SQLITE_JOURNAL",
                "DUCKDB_SPILL",
                "PARTIAL_WRITES",
                "CLOSURE_UNCERTAINTY",
            )
            else "DERIVED_RETAINED"
        )
        b.require(component["state_predicate"] == predicate, "B2_RS1_STATE_PREDICATE")
        # Every possible partial/failed allocation stays conservatively charged.
        b.require(component["retained_after_phase"] is True, "B2_RS1_NO_RECLAIM")
        b.require(
            component["max_simultaneous_instances"] == component["count_bound"],
            "B2_RS1_SIMULTANEOUS_BOUND",
        )
        amount, files, payload = component_bytes(component, model)
        physical, inodes, retained = (
            add(physical, amount),
            add(inodes, files),
            add(retained, payload),
        )
    b.require(
        (physical, inodes, retained)
        == (
            model["physical_peak_bound_bytes"],
            model["physical_inode_bound"],
            model["retained_payload_bound_bytes"],
        ),
        "B2_RS1_TOTAL_MISMATCH",
    )
    b.require(
        physical <= model["capacity_bytes"] and inodes <= model["capacity_inodes"],
        "B2_RS1_CAPACITY",
    )
    by_id = {x["component_id"]: x for x in components}
    for kind in COUNTS:
        b.require(
            sum(x["allocations"][kind] for x in commands) == by_id[kind]["count_bound"],
            "B2_RS1_COMMAND_COVERAGE",
        )
        if COUNTS[kind] == "commands":
            b.require(
                all(x["allocations"][kind] == 1 for x in commands),
                "B2_RS1_COMMAND_COVERAGE",
            )
    for command in commands:
        amounts = [
            component_bytes({**by_id[k], "count_bound": n}, model)
            for k, n in command["allocations"].items()
        ]
        b.require(
            command["max_generated_bytes"] == sum(x[0] for x in amounts)
            and command["max_generated_inodes"] == sum(x[1] for x in amounts),
            "B2_RS1_COMMAND_DERIVATION",
        )
    # Each command receives its entire maximum allocation before entry. All
    # commands' possible retained/failed outputs must fit the physical model.
    b.require(
        sum(x["max_generated_bytes"] for x in commands) <= physical
        and sum(x["max_generated_inodes"] for x in commands) <= inodes,
        "B2_RS1_COMMAND_ENVELOPE",
    )
    return {"physical_bytes": physical, "inodes": inodes, "payload_bytes": retained}


def workload_binding(plan):
    """Exact non-cyclic identity of the real plan, excluding RS1/profile links."""
    value = dict(plan)
    for name in (
        "operations_profile_sha256",
        "resource_retention_model_sha256",
        "resource_workload_sha256",
    ):
        value.pop(name, None)
    value["schema_version"] = b.REGISTRY["names"]["PLAN"]
    return b.digest(value)


def member_workload(plan):
    amounts = plan["budgets"]
    controls = add(
        amounts["required_control_observations"],
        amounts["reserved_control_observations"],
    )
    return {
        "plan_binding_sha256": workload_binding(plan),
        "data_works": amounts["data_observations"],
        "data_attempts": amounts["data_attempts"],
        "control_works": controls,
        "control_attempts": amounts["control_http_attempts"],
        "candidate_rows": mul(amounts["data_observations"], plan["result_limit"]),
        "events": amounts["event_count"],
        "ledger_rows": add(amounts["data_observations"], controls),
        "result_limit": plan["result_limit"],
    }


def aggregate_workload_hash(model):
    return b.digest(
        {
            "population_scope": model["population_scope"],
            "members": model["member_workloads"],
        }
    )


def validate_plan_model(model, plan):
    """Bind one exact member without resetting the aggregate retained model."""
    validate_model(model)
    member = member_workload(plan)
    b.require(
        model["population_scope"] == plan["population_scope"]
        and plan["resource_workload_sha256"] == member["plan_binding_sha256"]
        and sum(x == member for x in model["member_workloads"]) == 1,
        "B2_RS1_WORKLOAD_DERIVATION",
    )


def profile_schema():
    schema = dict(b.SCHEMAS[b.REGISTRY["names"]["PROFILE"]])
    schema["schema_version"] = "=" + PROFILE
    schema["resource_retention_model"] = MODEL_SCHEMA
    return schema


def plan_schema():
    schema = dict(b.SCHEMAS[b.REGISTRY["names"]["PLAN"]])
    schema["schema_version"] = "=" + PLAN
    schema["resource_retention_model_sha256"] = "D"
    schema["resource_workload_sha256"] = "D"
    return schema


def validate_record(value):
    version = value.get("schema_version")
    if version == MODEL:
        validate_model(value)
    elif version == PROFILE:
        shape(value, profile_schema())
        validate_model(value["resource_retention_model"])
    elif version == PLAN:
        shape(value, plan_schema())
    else:
        b.require(False, "B2_RS1_VERSION")


def parse(raw, expected=None):
    b.require(type(raw) is bytes and len(raw) <= b.MAX_METADATA, "B2_METADATA_LIMIT")
    value = io.metadata(raw)
    b.require(
        expected is None or value.get("schema_version") == expected, "B2_RS1_VERSION"
    )
    validate_record(value)
    return value


def authority_check(
    model, records, authority, *, now, source_hash, runtime_hash, workload_hash
):
    validate_model(model)
    b.require(model["valid_from"] <= now < model["valid_until"], "B2_RS1_EXPIRED")
    b.require(
        (
            model["source_inventory_sha256"],
            model["runtime_inventory_sha256"],
            model["workload_sha256"],
        )
        == (source_hash, runtime_hash, workload_hash),
        "B2_RS1_SOURCE_BINDING",
    )
    for field in (
        "review_sha256",
        "retry_state_proof_sha256",
        "capacity_record_sha256",
        "capacity_owner_authority_sha256",
        "filesystem_accounting_sha256",
        "codec_inventory_sha256",
        "encoding_inventory_sha256",
    ):
        records.raw(model[field])
        authority.require(
            "resource_retention_" + field.removesuffix("_sha256"), model[field], model
        )
    for item in (*model["components"], *model["commands"]):
        proof = item.get("evidence_sha256", item.get("bound_evidence_sha256"))
        records.raw(proof)
        authority.require("resource_retention_bound", proof, item)
    authority.require("resource_retention", b.digest(model), model)


def command_scope_record(config, *, plan_binding=None):
    """Canonical acyclic scope; model-derived records are bound separately.

    Profile, plan, campaign-start, admission and authority hashes may directly
    or indirectly contain the model hash and therefore cannot be inputs to a
    command scope stored inside that model. The exact plan member is supplied
    through its non-cyclic binding, while runtime authorities still bind the
    complete configuration independently.
    """
    runtime = config["runtime"]
    campaign = runtime["campaign"]
    b.require(
        (campaign is None and plan_binding is None)
        or (campaign is not None and type(plan_binding) is str),
        "B2_RS1_COMMAND_SCOPE",
    )
    if plan_binding is not None:
        b.validate_type(plan_binding, "D")
    stable_runtime = {
        name: runtime.get(name)
        for name in (
            "version",
            "population_scope",
            "mode",
            "phase",
            "source_root",
            "output_parent",
            "scratch_parent",
            "temporary_root",
            "phase_duration_ms",
            "phase_until",
            "phase_memory_bytes",
            "phase_disk_capacity_bytes",
            "phase_generation_bound_bytes",
            "phase_generation_max_files",
            "phase_generation_check_ms",
            "resource_evidence_sha256",
            "scientific_decision_sha256",
            "permission_sha256",
            "permission_current_path",
            "gate",
            "window_state_path",
            "response_rules_sha256",
            "transport",
            "postflight_bundle_path",
            "administration_owner_sha256",
            "local_preparation_current_path",
        )
    }
    stable_runtime["source_inventory_sha256"] = b.digest(runtime["source_files"])
    stable_campaign = None
    if campaign is not None:
        stable_campaign = {
            "plan_binding_sha256": plan_binding,
            "work_path": campaign["work_path"],
            "work_file_sha256": campaign["work_file_sha256"],
            "segment_path": campaign["segment_path"],
            "predecessor_path": campaign["predecessor_path"],
            "runtime_inventory_sha256": campaign["runtime_inventory_sha256"],
            "pause_after_ms": campaign["pause_after_ms"],
            "control_adapters": campaign["control_adapters"],
        }
    stable_config = {
        name: config.get(name)
        for name in (
            "input_binding_sha256",
            "catalog_path",
            "catalog_file_sha256",
            "C",
            "T",
            "capability_evidence_sha256",
            "depth_decision_sha256",
            "lineage_binding_sha256",
            "local_accepted_roots",
            "local_workload_sha256",
        )
    }
    return {
        "schema_version": ASSET["command_scope_version"],
        "runtime": stable_runtime,
        "campaign": stable_campaign,
        "configuration": stable_config,
    }


def command_scope(config, *, plan_binding=None):
    return b.digest(command_scope_record(config, plan_binding=plan_binding))


class CommandLedger:
    """Finite original-content ledger. Any unclosed or uncertain command blocks.

    One exclusive active claim, bounded original records, no overwrite. A
    successful result never erases charged commands or grants deletion credit.
    """

    def __init__(self, root, model, *, command_id, phase, scope_hash, check):
        validate_model(model)
        self.root, self.model, self.check = Path(root), model, check
        self.model_hash = b.digest(model)
        self.command_id, self.finished = b.uint(command_id, True), False
        b.require(command_id <= len(model["commands"]), "B2_RS1_COMMAND_EXHAUSTED")
        self.command = model["commands"][command_id - 1]
        b.require(
            self.command["phase"] == phase
            and self.command["scope_sha256"] == scope_hash,
            "B2_RS1_COMMAND_BINDING",
        )
        self.check()
        io.private_directory(self.root.parent)
        if not self.root.exists():
            b.require(command_id == 1, "B2_RS1_COMMAND_ORDER")
            io.reserve(self.root)
            io.write(self.root / "model.json", b.canonical(model))
        self._validate_prefix()
        self.check()
        # O_EXCL keeps the claim on any uncertain write. No cleanup releases it.
        self.claim = self.root / "ACTIVE.json"
        self.begin = {
            "schema_version": "stage12_resource_command_begin_b2_rs1_v1",
            "model_sha256": self.model_hash,
            "command_id": command_id,
            "command_sha256": b.digest(self.command),
        }
        io.write(self.claim, b.canonical(self.begin))
        self._validate_prefix(active=self.begin)
        self.check()

    def _validate_prefix(self, active=None):
        self.check()
        io.private_directory(self.root)
        b.require(
            io.read(self.root / "model.json") == b.canonical(self.model),
            "B2_RS1_MODEL_CHANGED",
        )
        expected = {"model.json"}
        previous = None
        total_bytes = total_inodes = 0
        for i in range(1, self.command_id):
            self.check()
            name = f"{i:06d}.json"
            expected.add(name)
            raw = io.read(self.root / name)
            row = io.metadata(raw)
            b.require(
                set(row)
                == {
                    "schema_version",
                    "model_sha256",
                    "command_id",
                    "command_sha256",
                    "previous_sha256",
                    "disposition",
                    "observed_bytes",
                    "observed_inodes",
                    "inventory_sha256",
                    "inventory_roots",
                    "inventory_max_entries",
                },
                "B2_RS1_LEDGER_SCHEMA",
            )
            b.require(
                row["schema_version"] == "stage12_resource_command_finish_b2_rs1_v1"
                and row["model_sha256"] == self.model_hash
                and row["command_id"] == i
                and row["command_sha256"] == b.digest(self.model["commands"][i - 1])
                and row["previous_sha256"] == previous
                and row["disposition"] == "COMPLETED",
                "B2_RS1_UNCLEAN_RECOVERY",
            )
            for key in ("observed_bytes", "observed_inodes"):
                b.uint(row[key])
            b.validate_type(row["inventory_sha256"], "D")
            roots = inventory_roots(row["inventory_roots"])
            b.uint(row["inventory_max_entries"], True)
            observed = generation_inventory(
                roots,
                max_entries=row["inventory_max_entries"],
                check=self.check,
            )
            b.require(
                observed
                == {
                    "bytes": row["observed_bytes"],
                    "entries": row["observed_inodes"],
                    "sha256": row["inventory_sha256"],
                },
                "B2_RS1_CUMULATIVE_INVENTORY_CHANGED",
            )
            command = self.model["commands"][i - 1]
            b.require(
                row["observed_bytes"] <= command["max_generated_bytes"]
                and row["observed_inodes"] <= command["max_generated_inodes"],
                "B2_RS1_COMMAND_BOUND",
            )
            total_bytes = add(total_bytes, command["max_generated_bytes"])
            total_inodes = add(total_inodes, command["max_generated_inodes"])
            previous = b.sha(raw).hex()
        if active is not None:
            expected.add("ACTIVE.json")
            b.require(
                io.read(self.root / "ACTIVE.json") == b.canonical(active),
                "B2_RS1_ACTIVE_CHANGED",
            )
        actual = set()
        with os.scandir(self.root) as entries:
            for entry in entries:
                self.check()
                b.require(len(actual) <= MAX_COMMANDS + 2, "B2_RS1_LEDGER_BOUND")
                actual.add(entry.name)
        b.require(actual == expected, "B2_RS1_UNCLEAN_RECOVERY")
        self.previous = previous
        return total_bytes, total_inodes

    def observe(self, *, physical_bytes, inodes):
        self.check()
        b.uint(physical_bytes)
        b.uint(inodes)
        b.require(
            physical_bytes <= self.command["max_generated_bytes"]
            and inodes <= self.command["max_generated_inodes"],
            "B2_RS1_COMMAND_BOUND",
        )

    def finish(self, *, roots, max_entries):
        b.require(not self.finished, "B2_RS1_ALREADY_FINISHED")
        roots = inventory_roots([str(Path(x)) for x in roots])
        b.uint(max_entries, True)
        inventory = generation_inventory(
            roots, max_entries=max_entries, check=self.check
        )
        self.observe(physical_bytes=inventory["bytes"], inodes=inventory["entries"])
        self._validate_prefix(active=self.begin)
        row = {
            "schema_version": "stage12_resource_command_finish_b2_rs1_v1",
            "model_sha256": self.model_hash,
            "command_id": self.command_id,
            "command_sha256": b.digest(self.command),
            "previous_sha256": self.previous,
            "disposition": "COMPLETED",
            "observed_bytes": inventory["bytes"],
            "observed_inodes": inventory["entries"],
            "inventory_sha256": inventory["sha256"],
            "inventory_roots": [str(x) for x in roots],
            "inventory_max_entries": max_entries,
        }
        self.check()
        target = self.root / f"{self.command_id:06d}.json"
        io.write(target, b.canonical(row))
        b.require(io.read(target) == b.canonical(row), "B2_RS1_LEDGER_CHANGED")
        self.check()
        b.require(
            io.read(self.claim) == b.canonical(self.begin), "B2_RS1_ACTIVE_CHANGED"
        )
        # A mutation after preparation but before commit leaves ACTIVE in place.
        b.require(
            generation_inventory(roots, max_entries=max_entries, check=self.check)
            == inventory,
            "B2_RS1_CUMULATIVE_INVENTORY_CHANGED",
        )
        self.claim.unlink()
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.finished = True
        return b.digest(row)


def inventory_roots(values):
    b.require(type(values) is list and 0 < len(values) <= 16, "B2_RS1_INVENTORY_BOUND")
    roots = [Path(x) for x in values]
    b.require(
        all(x.is_absolute() and ".." not in x.parts for x in roots)
        and len(set(roots)) == len(roots)
        and all(not x.is_relative_to(y) for x in roots for y in roots if x != y),
        "B2_RS1_INVENTORY_PATH",
    )
    return roots


def generation_inventory(roots, *, max_entries, check):
    """Fresh exact content/path/type/mode identity, bounded traversal state.

    Used at RS1 command close, not as an indefinite validated-evidence cache.
    Caller roots are the existing runtime's exclusive generated namespaces.
    """
    b.uint(max_entries, True)
    digest = hashlib.sha256()
    count = total = 0
    # Directory enumeration order does not affect the commutative identity;
    # each framed path/content hash appears once and count is also bound.
    accumulator = 0
    bindings = []

    def signature(st):
        return (
            st.st_dev,
            st.st_ino,
            st.st_mode,
            st.st_uid,
            st.st_gid,
            st.st_size,
            st.st_mtime_ns,
            st.st_ctime_ns,
            st.st_nlink,
            st.st_blocks,
        )

    for root in roots:
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack:
            check()
            path, depth = stack.pop()
            b.require(depth <= 64, "B2_RS1_INVENTORY_BOUND")
            before = path.stat(follow_symlinks=False)
            b.require(
                before.st_uid == os.getuid()
                and before.st_mode & 0o077 == 0
                and not stat.S_ISLNK(before.st_mode),
                "B2_RS1_INVENTORY_PATH",
            )
            count += 1
            b.require(count <= max_entries, "B2_RS1_INVENTORY_BOUND")
            physical = max(before.st_size, before.st_blocks * 512)
            total = add(total, physical)
            rel = str(path.relative_to(root))
            if stat.S_ISREG(before.st_mode):
                b.require(before.st_nlink == 1, "B2_RS1_INVENTORY_PATH")
                h = hashlib.sha256()
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as stream:
                    b.require(
                        (
                            os.fstat(stream.fileno()).st_dev,
                            os.fstat(stream.fileno()).st_ino,
                        )
                        == (before.st_dev, before.st_ino),
                        "B2_RS1_INVENTORY_CHANGED",
                    )
                    while block := stream.read(65536):
                        check()
                        h.update(block)
                    after_fd = os.fstat(stream.fileno())
                content = h.hexdigest()
                b.require(
                    signature(before)
                    == signature(after_fd)
                    == signature(path.stat(follow_symlinks=False)),
                    "B2_RS1_INVENTORY_CHANGED",
                )
            elif stat.S_ISDIR(before.st_mode):
                content = None
                with os.scandir(path) as entries:
                    for entry in entries:
                        b.require(len(stack) < max_entries, "B2_RS1_INVENTORY_BOUND")
                        stack.append((Path(entry.path), depth + 1))
                b.require(
                    signature(before) == signature(path.stat(follow_symlinks=False)),
                    "B2_RS1_INVENTORY_CHANGED",
                )
            else:
                b.require(False, "B2_RS1_INVENTORY_PATH")
            bindings.append((path, signature(before)))
            identity = b.canonical(
                {
                    "root": str(root),
                    "relative": rel,
                    "physical_bytes": physical,
                    "device": before.st_dev,
                    "inode": before.st_ino,
                    "mode": before.st_mode,
                    "content": content,
                }
            )
            accumulator = (accumulator + int.from_bytes(b.sha(identity), "big")) % (
                1 << 256
            )
    for path, original in bindings:
        check()
        b.require(
            signature(path.stat(follow_symlinks=False)) == original,
            "B2_RS1_INVENTORY_CHANGED",
        )
    digest.update(
        b.canonical(
            {
                "entry_count": count,
                "physical_bytes": total,
                "entry_hash_sum": f"{accumulator:064x}",
            }
        )
    )
    return {"bytes": total, "entries": count, "sha256": digest.hexdigest()}

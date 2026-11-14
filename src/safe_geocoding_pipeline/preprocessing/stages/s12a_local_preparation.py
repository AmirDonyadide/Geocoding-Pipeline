"""Scientific 12A only: accepted DEVELOPMENT catalog, lineage and full reopen.

This separate authority cannot authorize a probe, calibration, transfer or any
later stage. Source provenance is read from accepted artifacts, never raw CSV.
The witness interpretation is UNKNOWN throughout; memberships are diagnostics.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from ...execution_policy import require_goethe_nhr_slurm
from . import s11_semantic_input as accepted10
from . import s12_b2_catalog as catalog
from . import s12_b2_contract as b
from . import s12_b2_lineage as lineage
from . import s12_storage as io

VERSION = "stage12a_catalog_lineage_local_v1"
OPERATION = "BUILD_VALIDATE_REOPEN"
CONTROLLED_ROOT = Path(
    "/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/12a"
)
OWNER_INSTRUCTION_SHA256 = (
    "1d829225cac40dac81a6a6017021b0f439ba0eb3de32d4e7a03e62211d6167e9"
)
VALIDATED_PAYLOAD_BYTES = 1500838085
OPERATING_POLICY = "stage12a_operating_43200_v1"
PROGRESS_VERSION = "stage12a_fixed_boundary_progress_v1"
MAX_PROGRESS_BYTES = 32 * 512
OPERATING_DECISION_SHA256 = (
    "8f15787a2b40599aef6d2a82a5ec975b108a42c01100e16d5b500e89ebb5037d"
)
PROGRESS_LABELS = (
    "ACCEPTED_INPUT_PASS_1_BEGIN",
    "ACCEPTED_INPUT_PASS_1_END",
    "LINEAGE_CTOR_BEGIN",
    "LINEAGE_REFERENCE_REGISTRY_BEGIN",
    "LINEAGE_REFERENCE_REGISTRY_END",
    "LINEAGE_REFERENCE_CAPABILITIES_BEGIN",
    "LINEAGE_REFERENCE_CAPABILITIES_END",
    "LINEAGE_REFERENCE_OBJECTS_BEGIN",
    "LINEAGE_REFERENCE_OBJECTS_END",
    "LINEAGE_REFERENCE_MEMBERS_BEGIN",
    "LINEAGE_REFERENCE_MEMBERS_END",
    "LINEAGE_EVIDENCE_BEGIN",
    "LINEAGE_EVIDENCE_END",
    "LINEAGE_SOURCE_RELATIONS_BEGIN",
    "LINEAGE_SOURCE_RELATIONS_END",
    "LINEAGE_OCCURRENCES_BEGIN",
    "LINEAGE_OCCURRENCES_END",
    "ACCEPTED_INPUT_PASS_2_BEGIN",
    "ACCEPTED_INPUT_PASS_2_END",
    "LINEAGE_CTOR_END",
    "CATALOG_BUILD_BEGIN",
    "ACCEPTED_INPUT_PASS_3_BEGIN",
    "ACCEPTED_INPUT_PASS_3_END",
    "LINEAGE_CONTEXT_PROJECTION_BEGIN",
    "LINEAGE_CONTEXT_PROJECTION_END",
    "ACCEPTED_INPUT_PASS_4_BEGIN",
    "ACCEPTED_INPUT_PASS_4_END",
    "CATALOG_BUILD_END",
    "ACCEPTED_INPUT_PASS_5_BEGIN",
    "ACCEPTED_INPUT_PASS_5_END",
    "ARTIFACT_REOPEN_BEGIN",
    "ARTIFACT_REOPEN_END",
)
_STAGE = "CONFIGURATION"
INTERPRETATION = {
    "country_namespace": "UNKNOWN",
    "candidate_levels": {
        k: "UNKNOWN"
        for k in ("locality", "localadmin", "county", "region", "macroregion")
    },
    "source_levels": {"city": "UNKNOWN", "region": "UNKNOWN"},
}
EXPECTED_COUNTS = {
    "sources": 35000,
    "contexts": 69747,
    "semantic_requests": 105805,
    "hypothesis_links": 142677,
    "mapping_links": 142677,
    "standard_contexts": 34822,
    "native_contexts": 34925,
    "family_decisions": 418482,
    "eligible_family_links": 172112,
    "zero_query_contexts": 1668,
    "sources_without_context": 0,
}


def selected_operating_policy(config):
    """Only an explicit closed successor selects the longer finite operation."""
    if "operating_policy" not in config:
        return None
    value = config["operating_policy"]
    b.require(
        type(value) is dict
        and set(value)
        == {
            "schema_version",
            "application_seconds",
            "scheduler_seconds",
            "progress_policy",
            "decision_record_path",
            "decision_record_sha256",
        }
        and value["schema_version"] == OPERATING_POLICY
        and type(value["application_seconds"]) is int
        and value["application_seconds"] == 43200
        and type(value["scheduler_seconds"]) is int
        and value["scheduler_seconds"] == 44100
        and value["progress_policy"] == PROGRESS_VERSION
        and value["decision_record_sha256"] == OPERATING_DECISION_SHA256
        and type(value["decision_record_path"]) is str,
        "S12A_OPERATING_POLICY",
    )
    return value


def validate_operating_entry(config, environment):
    policy = selected_operating_policy(config)
    b.require(
        (
            policy is None
            and "STAGE12A_OPERATING_POLICY" not in environment
            and "STAGE12A_SCHEDULER_SECONDS" not in environment
        )
        or (
            policy is not None
            and environment.get("STAGE12A_OPERATING_POLICY") == OPERATING_POLICY
            and environment.get("STAGE12A_SCHEDULER_SECONDS") == "44100"
        ),
        "S12A_OPERATING_ENTRY",
    )


def validate_config(value):
    b.require(
        type(value) is dict
        and set(value)
        == {
            "schema_version",
            "operation",
            "population_scope",
            "network",
            "holdout",
            "source_git_sha",
            "authorization_record_path",
            "authorization_record_sha256",
            "owner_instruction_record_path",
            "owner_instruction_record_sha256",
            "input_binding",
            "accepted_roots",
            "output_path",
            "scratch_path",
            "resources",
        }
        | ({"operating_policy"} if "operating_policy" in value else set())
        and value["schema_version"] == VERSION
        and value["operation"] == OPERATION
        and value["population_scope"] == b.DEVELOPMENT
        and value["network"] == "DENY_ALL"
        and value["holdout"] == "EXCLUDED",
        "S12A_LOCAL_SCOPE",
    )
    policy = selected_operating_policy(value)
    b.require(
        type(value["source_git_sha"]) is str
        and len(value["source_git_sha"]) == 40
        and all(x in "0123456789abcdef" for x in value["source_git_sha"]),
        "S12A_SOURCE_BINDING",
    )
    b.validate_type(value["authorization_record_sha256"], "D")
    b.require(
        value["owner_instruction_record_sha256"] == OWNER_INSTRUCTION_SHA256,
        "S12A_OWNER_INSTRUCTION",
    )
    b.validate(value["input_binding"], "stage12_stage11_input_binding_b2_v1")
    b.require(
        value["input_binding"]["population_scope"] == b.DEVELOPMENT
        and all(value["input_binding"][k] == v for k, v in catalog.ACCEPTED.items()),
        "S12A_INPUT_BINDING",
    )
    b.require(
        type(value["accepted_roots"]) is dict
        and set(value["accepted_roots"])
        == {"stage06", "stage08", "stage09", "stage11"},
        "S12A_INPUT_BINDING",
    )
    paths = [
        *value["accepted_roots"].values(),
        *(
            value[k]
            for k in (
                "authorization_record_path",
                "owner_instruction_record_path",
                "output_path",
                "scratch_path",
            )
        ),
    ]
    if policy is not None:
        paths.append(policy["decision_record_path"])
    b.require(
        all(
            type(x) is str
            and Path(x).is_absolute()
            and not any(part in x.lower() for part in ("holdout", "/production/"))
            and not Path(x).is_relative_to(Path("/scratch"))
            for x in paths
        ),
        "S12A_PATH_SCOPE",
    )
    out, scratch = Path(value["output_path"]), Path(value["scratch_path"])
    for field, child in (
        ("output_path", "artifacts"),
        ("scratch_path", "scratch"),
        ("authorization_record_path", "controls"),
        ("owner_instruction_record_path", "controls"),
    ):
        path = Path(value[field])
        b.require(
            str(path) == value[field]
            and ".." not in path.parts
            and path != CONTROLLED_ROOT / child
            and path.is_relative_to(CONTROLLED_ROOT / child),
            "S12A_CONTROLLED_LOCATION",
        )
    if policy is not None:
        path = Path(policy["decision_record_path"])
        b.require(
            str(path) == policy["decision_record_path"]
            and ".." not in path.parts
            and path != CONTROLLED_ROOT / "controls"
            and path.is_relative_to(CONTROLLED_ROOT / "controls"),
            "S12A_CONTROLLED_LOCATION",
        )
    b.require(
        out != scratch
        and not out.is_relative_to(scratch)
        and not scratch.is_relative_to(out),
        "S12A_PATH_SCOPE",
    )
    for raw in value["accepted_roots"].values():
        root = Path(raw)
        b.require(
            all(
                root != target
                and not root.is_relative_to(target)
                and not target.is_relative_to(root)
                for target in (out, scratch)
            ),
            "S12A_PATH_SCOPE",
        )
    resources = value["resources"]
    b.require(
        type(resources) is dict
        and set(resources)
        == {
            "duckdb_memory_bytes",
            "max_duration_seconds",
            "max_generated_disk_bytes",
            "minimum_free_bytes",
        },
        "S12A_RESOURCE_SCOPE",
    )
    for limit in resources.values():
        b.uint(limit, True)
    b.require(
        resources["duckdb_memory_bytes"] == 4 * 2**30
        and (
            resources["max_duration_seconds"] <= 7200
            if policy is None
            else resources["max_duration_seconds"] == 43200
        )
        and resources["max_generated_disk_bytes"]
        >= max(64 * 2**30, 32 * VALIDATED_PAYLOAD_BYTES)
        and resources["minimum_free_bytes"]
        >= 2 * resources["max_generated_disk_bytes"],
        "S12A_RESOURCE_SCOPE",
    )
    return value


def check_duration(started, maximum):
    now = time.monotonic()
    b.require(now - started < maximum, "S12A_RUNTIME_LIMIT")
    return now


class Progress:
    """At most 32 closed records; same run origin, private durable journal."""

    def __init__(self, path, *, started, check, output=None):
        self.started, self.check, self.count = started, check, 0
        self.path, self.bytes = path, 0
        self.emitted_sha256 = hashlib.sha256()
        self.output = (
            (
                lambda row: print(
                    json.dumps(row, sort_keys=True, separators=(",", ":")), flush=True
                )
            )
            if output is None
            else output
        )
        io.write(path, b"")
        self.fd = os.open(path, os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW)
        self.identity = os.fstat(self.fd)

    def __call__(self, label):
        self.check()
        b.require(
            self.count < len(PROGRESS_LABELS) and label == PROGRESS_LABELS[self.count],
            "S12A_PROGRESS_BOUNDARY",
        )
        elapsed = int((time.monotonic() - self.started) * 1000)
        b.uint(elapsed)
        row = {
            "schema_version": PROGRESS_VERSION,
            "sequence": self.count + 1,
            "boundary": label,
            "elapsed_ms": elapsed,
        }
        raw = b.canonical(row)
        b.require(
            len(raw) <= 512 and self.bytes + len(raw) <= MAX_PROGRESS_BYTES,
            "S12A_PROGRESS_BOUNDARY",
        )
        b.require(os.write(self.fd, raw) == len(raw), "S12A_PROGRESS_WRITE")
        os.fsync(self.fd)
        self.emitted_sha256.update(raw)
        self.count += 1
        self.bytes += len(raw)
        self.output(row)
        self.check()

    def snapshot(self):
        self.check()
        b.require(self.count == len(PROGRESS_LABELS), "S12A_PROGRESS_INCOMPLETE")
        os.fsync(self.fd)
        info = self.path.lstat()
        b.require(
            not self.path.is_symlink()
            and info.st_uid == os.geteuid()
            and info.st_nlink == 1
            and info.st_mode & 0o777 == 0o600
            and (info.st_dev, info.st_ino)
            == (self.identity.st_dev, self.identity.st_ino),
            "S12A_PROGRESS_CHANGED",
        )
        raw = io.read(self.path, limit=MAX_PROGRESS_BYTES)
        b.require(
            b.sha(raw).hex() == self.emitted_sha256.hexdigest(), "S12A_PROGRESS_CHANGED"
        )
        rows = [io.metadata(line + b"\n") for line in raw.splitlines()]
        b.require(
            len(raw) == self.bytes
            and len(rows) == self.count
            and all(
                set(row) == {"schema_version", "sequence", "boundary", "elapsed_ms"}
                and row["schema_version"] == PROGRESS_VERSION
                and row["sequence"] == index
                and row["boundary"] == PROGRESS_LABELS[index - 1]
                and type(row["elapsed_ms"]) is int
                and 0 <= row["elapsed_ms"]
                for index, row in enumerate(rows, 1)
            )
            and [row["elapsed_ms"] for row in rows]
            == sorted(row["elapsed_ms"] for row in rows),
            "S12A_PROGRESS_CHANGED",
        )
        after = self.path.lstat()
        b.require(
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
            "S12A_PROGRESS_CHANGED",
        )
        self.check()
        return {
            "schema_version": PROGRESS_VERSION,
            "records": self.count,
            "bytes": len(raw),
            "sha256": b.sha(raw).hex(),
            "max_records": 32,
            "max_bytes": MAX_PROGRESS_BYTES,
            "durability": "FSYNC_PER_RECORD_AND_FULL_READ_BEFORE_RESULT",
            "scope": "SUPPLEMENTARY_OUTSIDE_ARTIFACT",
            "lifetime": "PRESERVE_WITH_RUN",
        }

    def close(self):
        if self.fd is not None:
            descriptor, self.fd = self.fd, None
            os.close(descriptor)


class Authority:
    """Exact 12A binding; no service or downstream operation is expressible."""

    def __init__(self, config, guard, check):
        self.config = validate_config(config)
        self.guard, self.check = guard, check
        self.projection = None
        self.context = None

    def require(self, purpose, digest, context):
        self.guard.assert_active()
        self.check()
        allowed = {
            "protected_input",
            "protected_lineage_input",
            "witness_interpretation",
            "lineage_projection",
            "lineage_context",
        }
        b.require(purpose in allowed, "S12A_OPERATION_DENIED")
        if purpose == "protected_input":
            b.require(
                context == self.config["input_binding"] and digest == b.digest(context),
                "S12A_INPUT_BINDING",
            )
        elif purpose in {"protected_lineage_input", "witness_interpretation"}:
            b.require(
                context == INTERPRETATION and digest == b.digest(INTERPRETATION),
                "S12A_INTERPRETATION",
            )
        elif purpose == "lineage_projection":
            b.require(
                self.projection is not None
                and digest == self.projection.binding_sha256
                and context == {"input": self.config["input_binding"]},
                "S12A_LINEAGE_BINDING",
            )
        else:
            b.require(
                self.context == (digest, b.digest(context)), "S12A_LINEAGE_BINDING"
            )

    def bind_projection(self, projection):
        b.require(
            type(projection) is lineage.LineageProjection
            and projection.population_scope == b.DEVELOPMENT,
            "S12A_LINEAGE_BINDING",
        )
        self.projection = projection
        original = projection.rows

        def rows():
            for row in original():
                self.context = (row["origin_sha256"], b.digest({**row, "channels": []}))
                try:
                    yield row
                finally:
                    self.context = None

        projection.rows = rows


def _tree_bytes(root):
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(directory) / name
            b.require(not path.is_symlink(), "S12A_GENERATION_IDENTITY")
            mode = path.stat().st_mode & 0o777
            b.require(
                mode == (0o700 if path.is_dir() else 0o600),
                "S12A_GENERATION_PERMISSIONS",
            )
            if path.is_file():
                total += path.stat().st_size
    return total


def authorization_record(config):
    """Concrete session grant binding; generated only after source review/commit."""
    return {
        "schema_version": "stage12a_local_authorization_v1",
        "operation": OPERATION,
        "population_scope": b.DEVELOPMENT,
        "network": "DENY_ALL",
        "holdout": "EXCLUDED",
        "owner_instruction_record_sha256": config["owner_instruction_record_sha256"],
        "authority_provenance": "RELAYED_STANDING_OWNER_DELEGATION",
        "manager_approval": "OWNER_REPORTED_NOT_EXTERNAL_ATTESTATION",
        "configuration_sha256": b.digest(
            {
                k: v
                for k, v in config.items()
                if k not in {"authorization_record_path", "authorization_record_sha256"}
            }
        ),
    }


def artifact_seal(config, catalog_sha, provenance_sha):
    return {
        "schema_version": VERSION,
        "catalog_sha256": catalog_sha,
        "input_binding_sha256": b.digest(config["input_binding"]),
        "configuration_sha256": b.digest(config),
        "input_provenance_sha256": provenance_sha,
    }


def validate_provenance(provenance, config):
    if config["input_binding"]["population_scope"] == b.SYNTHETIC:
        b.require(provenance == {"SYNTHETIC_ONLY": True}, "S12A_PROVENANCE")
        return
    b.require(
        set(provenance)
        == {
            "stage11_manifest",
            "stage10_binding",
            "lineage_binding",
            "lineage_projection_sha256",
        },
        "S12A_PROVENANCE",
    )

    p, manifests = provenance["lineage_binding"], provenance["stage11_manifest"]
    b.require(
        p["split"] == "DEVELOPMENT"
        and all(
            p[k]["manifest_sha256"] == v
            for k, v in {
                "stage08": lineage.inputs.accepted8.STAGE08_MANIFEST_SHA256,
                "stage09": lineage.inputs.STAGE09_MANIFEST,
                "stage06_row_map": lineage.inputs.STAGE06_MANIFEST,
            }.items()
        )
        and p["stage09"]["reference_pack"]["manifest_sha256"]
        == lineage.inputs.PUBLIC_MANIFEST
        and manifests["split"] == "DEVELOPMENT"
        and manifests["logical_sha256"] == config["input_binding"]["dataset_sha256"]
        and manifests["input_binding"] == provenance["stage10_binding"]
        and provenance["stage10_binding"]["stage10"]["manifest_sha256"]
        == accepted10.MANIFEST_SHA,
        "S12A_PROVENANCE",
    )
    accepted_identifier = lineage.s10.identity(
        "stage10-input:v1", lineage.s10.canonical(p)
    ).hex()
    b.require(
        provenance["lineage_projection_sha256"]
        == b.digest(
            {
                "accepted_input_sha256": accepted_identifier,
                "interpretation_sha256": b.digest(INTERPRETATION),
                "algorithm": "stage12_accepted_lineage_projection_b2_v1",
            }
        ),
        "S12A_PROVENANCE",
    )


def input_graph(provenance):
    """Manifest-listed validated payload/summary graph, with no source rows.

    Governing manifests, success/commit seals and registration controls are
    separately bound and validated by the original accepted readers. This is
    a resource basis, not a syscall count or total physical-I/O claim.
    """
    result = []

    def add(stage, root, files):
        for item in files:
            result.append(
                {
                    "stage": stage,
                    "root": root,
                    "relative_path": item["relative_path"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }
            )

    binding = provenance["lineage_binding"]
    for stage in ("stage06_row_map", "stage08", "stage09"):
        item = binding[stage]
        add(stage, item["approved_anchor"], item["files"])
    pack = binding["stage09"]["reference_pack"]
    for relation in pack["relations"]:
        add("public_reference_pack", pack["approved_anchor"], relation["files"])
    add(
        "public_reference_pack",
        pack["approved_anchor"],
        pack["reference_index"]["files"],
    )
    stage10 = provenance["stage10_binding"]["stage10"]
    for relation in stage10["relations"]:
        add("stage10", stage10["approved_anchor"], relation["files"])
    add("stage10", stage10["approved_anchor"], stage10["metadata_inventory"])
    for relation in provenance["stage11_manifest"]["relations"]:
        add("stage11", "ACCEPTED_STAGE11_ROOT_IN_CONFIGURATION", relation["files"])
    add(
        "stage11",
        "ACCEPTED_STAGE11_ROOT_IN_CONFIGURATION",
        provenance["stage11_manifest"]["metadata_inventory"],
    )
    result.sort(key=lambda x: (x["stage"], x["root"], x["relative_path"]))
    b.require(
        len({(x["stage"], x["root"], x["relative_path"]) for x in result})
        == len(result),
        "S12A_PROVENANCE",
    )
    return result


def reopen_artifact(
    root, config, *, expected_counts=EXPECTED_COUNTS, check=lambda: None
):
    """Read-only complete artifact opener, including original seal and binding."""
    root = Path(root)
    io.private_directory(root)
    names = {"catalog.sqlite", "binding.json", "accepted_inputs.json", "_COMMITTED"}

    def identities():
        b.require({p.name for p in root.iterdir()} == names, "S12A_ARTIFACT_MEMBERSHIP")
        result = {}
        for path in (root, *(root / name for name in sorted(names))):
            info = path.lstat()
            b.require(
                not path.is_symlink()
                and (info.st_mode & 0o777) == (0o700 if path == root else 0o600)
                and (path == root or info.st_nlink == 1),
                "S12A_ARTIFACT_IDENTITY",
            )
            result[path.name] = (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mode,
                info.st_uid,
                info.st_nlink,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )
        return result

    before = identities()
    binding_raw = io.read(root / "binding.json", limit=b.MAX_METADATA)
    seal_raw = io.read(root / "_COMMITTED", limit=b.MAX_METADATA)
    provenance_raw = io.read(root / "accepted_inputs.json", limit=16 * 2**20)
    provenance = io.metadata(provenance_raw)
    validate_provenance(provenance, config)
    b.require(
        binding_raw == b.canonical(config["input_binding"]), "S12A_ARTIFACT_BINDING"
    )
    seal = io.metadata(seal_raw)
    b.validate_type(seal.get("catalog_sha256"), "D")
    b.require(
        seal_raw
        == b.canonical(
            artifact_seal(config, seal["catalog_sha256"], b.sha(provenance_raw).hex())
        ),
        "S12A_ARTIFACT_SEAL",
    )
    opened = catalog.Catalog(
        root / "catalog.sqlite",
        config["input_binding"],
        expected_file_sha256=seal["catalog_sha256"],
        read_only=True,
    )
    try:
        check()
        opened.verify()
        counts = opened.validate_relations(expected_counts)
        check()
        opened.verify()
    finally:
        opened.close()
    b.require(
        before == identities()
        and io.read(root / "binding.json", limit=b.MAX_METADATA) == binding_raw
        and io.read(root / "_COMMITTED", limit=b.MAX_METADATA) == seal_raw
        and io.read(root / "accepted_inputs.json", limit=16 * 2**20) == provenance_raw
        and catalog.s11.sha256_file(root / "catalog.sqlite") == seal["catalog_sha256"],
        "S12A_ARTIFACT_CHANGED",
    )
    return {"catalog_sha256": seal["catalog_sha256"], "counts": counts}


def run(config, *, repository):
    """One native invocation; preserves failed attempts and never resumes them."""
    global _STAGE
    entry_started = time.monotonic()
    _STAGE = "SITE_SOURCE_VALIDATE"
    require_goethe_nhr_slurm("scientific Stage12A catalog/lineage")
    config = validate_config(config)
    policy = selected_operating_policy(config)
    repository = Path(repository)
    # Git is local/read-only and completes before process-wide process denial.
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repository,
        text=True,
    )
    b.require(sha == config["source_git_sha"] and not dirty, "S12A_SOURCE_BINDING")
    from .s12_b2_runtime import OfflineGuard

    guard = OfflineGuard()
    old_umask = os.umask(0o077)
    projection = built = progress = None
    started = entry_started if policy is not None else time.monotonic()
    out, scratch = Path(config["output_path"]), Path(config["scratch_path"])
    bounds = config["resources"]
    last_disk_check = [0.0]
    parent_identities = {}

    def check(force=False):
        now = check_duration(started, bounds["max_duration_seconds"])
        if force or now - last_disk_check[0] >= 10:
            last_disk_check[0] = now
            for path, expected in parent_identities.items():
                info = path.lstat()
                b.require(
                    path.resolve(strict=True) == path
                    and (info.st_dev, info.st_ino, info.st_uid, info.st_mode)
                    == expected,
                    "S12A_CONTROLLED_LOCATION",
                )
            generated = sum(
                _tree_bytes(path) for path in (out, scratch) if path.exists()
            )
            b.require(
                generated <= bounds["max_generated_disk_bytes"], "S12A_DISK_LIMIT"
            )
            for path in (out.parent, scratch.parent):
                b.require(
                    shutil.disk_usage(path).free >= bounds["minimum_free_bytes"],
                    "S12A_FREE_SPACE",
                )
        guard.assert_active()

    try:
        _STAGE = "AUTHORITY_LOCATION_VALIDATE"
        controlled_paths = [
            config[field]
            for field in (
                "output_path",
                "scratch_path",
                "authorization_record_path",
                "owner_instruction_record_path",
            )
        ]
        if policy is not None:
            controlled_paths.append(policy["decision_record_path"])
        for raw_path in controlled_paths:
            parent = Path(raw_path).parent
            while parent.is_relative_to(CONTROLLED_ROOT):
                info = parent.lstat()
                b.require(
                    parent.resolve(strict=True) == parent
                    and parent.is_dir()
                    and info.st_uid == os.geteuid()
                    and info.st_mode & 0o777 == 0o700,
                    "S12A_CONTROLLED_LOCATION",
                )
                parent_identities[parent] = (
                    info.st_dev,
                    info.st_ino,
                    info.st_uid,
                    info.st_mode,
                )
                parent = parent.parent
        owner_raw = io.read(
            Path(config["owner_instruction_record_path"]), limit=16 * 2**20
        )
        b.require(
            b.sha(owner_raw).hex() == OWNER_INSTRUCTION_SHA256, "S12A_OWNER_INSTRUCTION"
        )
        raw = io.read(Path(config["authorization_record_path"]), limit=b.MAX_METADATA)
        b.require(
            b.sha(raw).hex() == config["authorization_record_sha256"],
            "S12A_AUTHORIZATION_BINDING",
        )
        authority_record = io.metadata(raw)
        b.require(
            authority_record == authorization_record(config),
            "S12A_AUTHORIZATION_SCOPE",
        )
        if policy is not None:
            decision_raw = io.read(
                Path(policy["decision_record_path"]), limit=b.MAX_METADATA
            )
            b.require(
                b.sha(decision_raw).hex() == OPERATING_DECISION_SHA256,
                "S12A_OPERATING_POLICY",
            )
        io.private_directory(out.parent)
        io.private_directory(scratch.parent)
        io.reserve(out)
        io.reserve(scratch)
        spill = scratch / "sqlite_spill"
        io.reserve(spill)
        b.require(
            os.environ.get("SQLITE_TMPDIR") == str(spill), "B2_PRIVATE_SPILL_REQUIRED"
        )
        check(True)
        if policy is not None:
            progress = Progress(out / "progress.jsonl", started=started, check=check)
        authority = Authority(config, guard, check)
        roots = {k: Path(v) for k, v in config["accepted_roots"].items()}
        with io.cooperative_io(check):
            _STAGE = "LINEAGE_INPUT_VALIDATE"
            projection = lineage.LineageProjection.open(
                stage08_root=roots["stage08"],
                stage09_root=roots["stage09"],
                stage06_root=roots["stage06"],
                scratch=scratch / "lineage",
                memory_bytes=bounds["duckdb_memory_bytes"],
                authority=authority,
                interpretation=INTERPRETATION,
                interpretation_sha256=b.digest(INTERPRETATION),
                **({"progress": progress} if progress is not None else {}),
            )
            authority.bind_projection(projection)
            _STAGE = "CATALOG_BUILD"
            pending = out / "building"
            io.reserve(pending)
            if progress is not None:
                progress("CATALOG_BUILD_BEGIN")
            built = catalog.build_accepted(
                pending / "catalog.sqlite",
                roots["stage11"],
                config["input_binding"],
                repository=repository,
                lineage=projection,
                authority=authority,
                scratch=scratch / "stage10",
                memory_bytes=bounds["duckdb_memory_bytes"],
            )
            if progress is not None:
                progress("CATALOG_BUILD_END")
            _STAGE = "CATALOG_VALIDATE"
            counts = built.validate_relations(EXPECTED_COUNTS)
            catalog_sha = built.file_sha256
            provenance = built.input_provenance
            validate_provenance(provenance, config)
            graph = input_graph(provenance)
            selected_input_bytes = sum(item["bytes"] for item in graph)
            b.require(
                bounds["max_generated_disk_bytes"]
                >= max(64 * 2**30, 32 * selected_input_bytes),
                "S12A_DISK_LIMIT",
            )
            provenance_raw = b.canonical(provenance)
            lineage_input_sha = projection.accepted.identifier.hex()
            lineage_projection_sha = projection.binding_sha256
            built.close()
            built = None
            _STAGE = "LINEAGE_REVALIDATE"
            projection.validate()
            projection.close()
            projection = None
            # Finish the private artifact, then atomically expose its new name.
            _STAGE = "ARTIFACT_SEAL"
            io.write(pending / "binding.json", b.canonical(config["input_binding"]))
            io.write(pending / "accepted_inputs.json", provenance_raw)
            io.write(
                pending / "_COMMITTED",
                b.canonical(
                    artifact_seal(config, catalog_sha, b.sha(provenance_raw).hex())
                ),
            )
            artifact = out / "artifact"
            b.require(not artifact.exists(), "S12A_OUTPUT_EXISTS")
            os.rename(pending, artifact)
            io.fsync_directory(out)
            _STAGE = "ARTIFACT_REOPEN"
            if progress is not None:
                progress("ARTIFACT_REOPEN_BEGIN")
            b.require(
                reopen_artifact(artifact, config, check=check)
                == {"catalog_sha256": catalog_sha, "counts": counts},
                "S12A_REOPEN_MISMATCH",
            )
            if progress is not None:
                progress("ARTIFACT_REOPEN_END")
            b.require(
                catalog.s11.sha256_file(artifact / "catalog.sqlite") == catalog_sha,
                "B2_CATALOG_CHANGED",
            )
            check(True)
            _STAGE = "RESULT_PUBLISH"
            result = {
                "schema_version": VERSION,
                "status": "BUILD_VALIDATE_REOPEN_PASS",
                "operation": OPERATION,
                "source_git_sha": sha,
                "authorization_record_sha256": config["authorization_record_sha256"],
                "configuration_sha256": b.digest(config),
                "catalog_sha256": catalog_sha,
                "input_provenance_sha256": b.sha(provenance_raw).hex(),
                "selected_input_graph_sha256": b.digest(graph),
                "selected_input_files": len(graph),
                "selected_input_bytes": selected_input_bytes,
                "input_graph_scope": "MANIFEST_LISTED_VALIDATED_PAYLOADS_AND_SUMMARIES",
                "resource_enforcement": "PERIODIC_APPLICATION_CHECKS_AND_SLURM_MEMORY_WALLTIME",
                "hard_physical_io_bound": "NOT_CLAIMED",
                "lineage_input_sha256": lineage_input_sha,
                "lineage_projection_sha256": lineage_projection_sha,
                "witness_interpretation_sha256": b.digest(INTERPRETATION),
                "owner_instruction_record_sha256": OWNER_INSTRUCTION_SHA256,
                "counts": counts,
                "network": "DENY_ALL",
                "holdout": "EXCLUDED",
                "witness_interpretation": "UNKNOWN",
                "memberships": "LINEAGE_DIAGNOSTIC_ONLY",
                "stage10_manifest_sha256": accepted10.MANIFEST_SHA,
                "stage11_manifest_sha256": catalog.ACCEPTED["manifest_sha256"],
            }
            if progress is not None:
                result["operating_policy"] = {
                    "schema_version": OPERATING_POLICY,
                    "application_seconds": 43200,
                    "scheduler_seconds": 44100,
                    "decision_record_sha256": OPERATING_DECISION_SHA256,
                }
                result["progress"] = progress.snapshot()
            io.write(out / "result.json", b.canonical(result))
            return result
    finally:
        finish((built, projection, progress), guard, old_umask, sys.exc_info()[1])


def finish(values, guard, old_umask, primary):
    global _STAGE
    failure = None
    try:
        for value in (*values, guard):
            if value is not None:
                try:
                    value.close()
                except BaseException as error:
                    if failure is None:
                        failure = error
    finally:
        os.umask(old_umask)
    if primary is None and failure is not None:
        _STAGE = "CLEANUP"
        raise failure


def safe_failure(error, stage):
    classes = {
        "Stage12Error",
        "Stage11Error",
        "Stage10Error",
        "ExecutionPolicyError",
        "OSError",
        "FileExistsError",
        "FileNotFoundError",
        "PermissionError",
        "MemoryError",
        "IntegrityError",
        "OperationalError",
        "ValueError",
        "KeyError",
        "TypeError",
    }
    codes = {
        "S12A_OPERATING_POLICY",
        "S12A_OPERATING_ENTRY",
        "S12A_PROGRESS_BOUNDARY",
        "S12A_PROGRESS_WRITE",
        "S12A_PROGRESS_INCOMPLETE",
        "S12A_PROGRESS_CHANGED",
        "S12A_CONFIGURATION_BINDING",
        "S12A_ARTIFACT_MEMBERSHIP",
        "S12A_ARTIFACT_BINDING",
        "S12A_ARTIFACT_SEAL",
        "S12A_ARTIFACT_CHANGED",
        "S12A_ARTIFACT_IDENTITY",
        "S12A_RESOURCE_SCOPE",
        "S12A_PATH_SCOPE",
        "S12A_INPUT_BINDING",
        "S12A_INTERPRETATION",
        "S12A_OPERATION_DENIED",
        "S12A_LINEAGE_BINDING",
        "S12A_OUTPUT_EXISTS",
        "S12A_GENERATION_IDENTITY",
        "S12A_GENERATION_PERMISSIONS",
        "S12A_LOCAL_SCOPE",
        "S12A_SOURCE_BINDING",
        "S12A_OWNER_INSTRUCTION",
        "S12A_AUTHORIZATION_BINDING",
        "S12A_AUTHORIZATION_SCOPE",
        "S12A_CONTROLLED_LOCATION",
        "S12A_RUNTIME_LIMIT",
        "S12A_DISK_LIMIT",
        "S12A_FREE_SPACE",
        "S12A_PROVENANCE",
        "S12A_REOPEN_MISMATCH",
        "B2_CATALOG_HASH",
        "B2_CATALOG_TOTALITY",
        "B2_CATALOG_INTEGRITY",
        "B2_CATALOG_RELATIONS",
        "B2_CATALOG_MEMBERSHIP",
        "B2_SOURCE_POPULATION",
        "B2_SOURCE_LINEAGE",
        "B2_OCCURRENCE_TOTALITY",
        "B2_PRIVATE_SPILL_REQUIRED",
        "B2_OFFLINE_NETWORK_PROCESS_DENIED",
    }
    stages = {
        "CONFIGURATION",
        "SITE_SOURCE_VALIDATE",
        "AUTHORITY_LOCATION_VALIDATE",
        "LINEAGE_INPUT_VALIDATE",
        "CATALOG_BUILD",
        "CATALOG_VALIDATE",
        "LINEAGE_REVALIDATE",
        "ARTIFACT_SEAL",
        "ARTIFACT_REOPEN",
        "RESULT_PUBLISH",
        "CLEANUP",
    }
    # Inspect only a string argument, never exception formatting or traceback.
    argument = error.args[0] if error.args and type(error.args[0]) is str else None
    return {
        "schema_version": VERSION,
        "status": "FAILED",
        "stage": stage if stage in stages else "CONFIGURATION",
        "exception_class": type(error).__name__
        if type(error).__name__ in classes
        else "UNCLASSIFIED_ERROR",
        "code": argument if argument in codes else "UPSTREAM_OR_UNCLASSIFIED_FAILURE",
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require_goethe_nhr_slurm("scientific Stage12A catalog/lineage configuration")
        b.require(
            args.configuration.is_relative_to(CONTROLLED_ROOT / "controls")
            and args.configuration.resolve(strict=True) == args.configuration,
            "S12A_CONTROLLED_LOCATION",
        )
        raw = io.read(args.configuration, limit=b.MAX_METADATA)
        b.require(
            b.sha(raw).hex() == os.environ.get("STAGE12A_CONFIGURATION_SHA"),
            "S12A_CONFIGURATION_BINDING",
        )
        config = io.metadata(raw)
        validate_operating_entry(config, os.environ)
        result = run(config, repository=Path(__file__).resolve().parents[4])
    except BaseException as error:
        print(
            json.dumps(
                safe_failure(error, _STAGE), sort_keys=True, separators=(",", ":")
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

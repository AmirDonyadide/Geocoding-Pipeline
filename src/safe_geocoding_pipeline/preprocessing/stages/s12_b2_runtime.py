"""Explicit DEVELOPMENT port for the unchanged observational phase algorithms.

The trust root is a separately reviewed, owner-provisioned private authority
registry. This module does not create permissions, operator evidence, grants or
signatures. Missing records fail closed. OFFLINE_ONLY cannot read a credential
provider or send traffic; the installed factory never constructs a test port.
"""

from __future__ import annotations

from array import array
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import os
import platform
import resource
import sqlite3
import stat
import tempfile
from pathlib import Path
import sys
import threading
import time

from . import s12_b2_contract as b
from . import s12_b2_catalog as catalogs
from . import s12_b2_evidence as evidence
from . import s12_b2_inventory as inventory
from . import s12_b2_local_preparation as local
from . import s12_b2_operations as operations
from . import s12_b2_phase_io as phase_io
from . import s12_b2_pipeline as pipeline
from . import s12_operations as transport_operations
from . import s12_response as response
from . import s12_storage as io
from . import s12_transport as transport
from . import s12_retrieval_contract as c

VERSION = "stage12_development_runtime_v1"
RA_VERSION = "stage12_development_runtime_b2_ra_g1_v1"
RA_AUTHORITY_VERSION = "stage12_development_runtime_authority_b2_ra_g1_v1"
RA_REPLACED = {"phase_memory_bytes", "phase_disk_capacity_bytes", "phase_generation_bound_bytes"}
RA_FIELDS = {"phase_monitor_selection_sha256", "phase_capacity_observation_sha256", "phase_logical_write_ceiling_bytes"}
AUTHORITY_VERSION = "stage12_development_runtime_authority_v1"
PREPARATION = frozenset(("build-catalog", "plan-calibration"))
DISPATCH = frozenset(("run-campaign", "run-direct-n"))
MAX_WORKS = 150000
MAX_WORK_BYTES = 8192
MAX_GRANTS = 4096
RUNTIME_FIELDS = frozenset(
    """version population_scope mode phase records_root
 authority_sha256 source_root source_files output_parent scratch_parent
 phase_duration_ms phase_until phase_memory_bytes phase_disk_capacity_bytes resource_evidence_sha256
 phase_generation_bound_bytes phase_generation_max_files phase_generation_check_ms temporary_root
 scientific_decision_sha256 permission_sha256 permission_current_path
 gate window_state_path response_rules_sha256 campaign transport
 postflight_bundle_path administration_owner_sha256""".split()
)
_GATE_FIELDS = frozenset(
    "window_hash permission_hash scientific_hash interpretation_hash binding_hash selection_hash".split()
)
_AUDIT_LOCK = threading.Lock()
_AUDIT_ACTIVE = 0
_AUDIT_INSTALLED = False
_PHASE_LOCK = threading.Lock()


def object_at(path, expected=None, limit=b.MAX_METADATA):
    raw = io.read(Path(path), limit=limit)
    if expected is not None:
        b.require(b.sha(raw).hex() == expected, "B2_RUNTIME_INPUT_CHANGED")
    return io.metadata(raw)


def absolute(path):
    b.require(
        type(path) is str and Path(path).is_absolute() and ".." not in Path(path).parts,
        "B2_RUNTIME_PATH",
    )
    return Path(path)


def under(path, parent):
    p, root = absolute(str(path)), absolute(str(parent))
    b.require(p != root and p.is_relative_to(root), "B2_RUNTIME_PATH")
    io.private_directory(root)
    # Existing private-path readers enforce symlink/ownership/type restrictions.
    return p


def scope_hash(config):
    """Break only the explicit registry/configuration hash cycle, not work scope."""
    value = dict(config)
    value["runtime"] = dict(config["runtime"])
    del value["runtime"]["authority_sha256"]
    return b.digest(value)


class Clock:
    def now_ns(self):
        return time.monotonic_ns()

    def utc(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def wait_until(self, deadline):
        while (left := deadline - self.now_ns()) > 0:
            time.sleep(min(left / 1e9, 0.05))


class OfflineGuard:
    """Process-wide audit denial during an offline port lifetime, including threads."""

    def __init__(self):
        global _AUDIT_INSTALLED, _AUDIT_ACTIVE
        with _AUDIT_LOCK:
            if not _AUDIT_INSTALLED:

                def audit(event, args):
                    if not _AUDIT_ACTIVE:
                        return
                    if event.startswith(
                        ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn")
                    ):
                        raise c.Stage12Error("B2_OFFLINE_NETWORK_PROCESS_DENIED")
                    if event == "open" and args and isinstance(args[0], (str, bytes)):
                        name = os.fsdecode(args[0]).lower()
                        if any(
                            token in name
                            for token in (
                                "pelias_api_key",
                                "/.ssh/",
                                "/.aws/",
                                "/holdout/",
                            )
                        ):
                            raise c.Stage12Error("B2_OFFLINE_PROTECTED_BOUNDARY")

                sys.addaudithook(audit)
                _AUDIT_INSTALLED = True
            _AUDIT_ACTIVE += 1
        self.closed = False

    def assert_active(self):
        b.require(
            not self.closed and _AUDIT_ACTIVE > 0 and _AUDIT_INSTALLED,
            "LP1_DENIAL_NOT_ACTIVE",
        )

    def close(self):
        global _AUDIT_ACTIVE
        with _AUDIT_LOCK:
            if not self.closed:
                _AUDIT_ACTIVE -= 1
                self.closed = True


class WorkFile:
    """Bounded offsets and hashes, with original per-row bytes reread on lookup.

    At most150000*(8+32) bytes of compact index storage. No query/response cache.
    New construction and verify() hash every original byte and validate the full
    work manifest. Indexed lookup checks original pathname/inode/size plus the
    actual row content hash, not an mtime or a cached validation boolean.
    """

    def __init__(self, path, expected, plan, check=lambda: None):
        self.path, self.expected, self.plan, self.check = (
            Path(path),
            expected,
            plan,
            check,
        )
        b.validate_type(expected, "D")
        self.offsets, self.hashes = array("Q"), bytearray()
        self.identity = None
        self.verify(build=True)

    def _open(self):
        io.private_directory(self.path.parent)
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            b.require(
                stat.S_ISREG(info.st_mode)
                and info.st_uid == os.getuid()
                and info.st_mode & 0o077 == 0
                and info.st_nlink == 1,
                "B2_RUNTIME_WORK_FILE",
            )
            actual = self.path.stat(follow_symlinks=False)
            identity = (info.st_dev, info.st_ino, info.st_size)
            b.require(
                (actual.st_dev, actual.st_ino, actual.st_size) == identity,
                "B2_RUNTIME_WORK_CHANGED",
            )
            if self.identity is None:
                self.identity = identity
            b.require(identity == self.identity, "B2_RUNTIME_WORK_CHANGED")
            return os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise

    def rows(self, *, build=False):
        hasher, count = hashlib.sha256(), 0
        with self._open() as stream:
            while True:
                self.check()
                offset = stream.tell()
                raw = stream.readline(MAX_WORK_BYTES + 1)
                if not raw:
                    break
                b.require(
                    raw.endswith(b"\n") and len(raw) <= MAX_WORK_BYTES,
                    "B2_RUNTIME_WORK_BOUND",
                )
                row = io.metadata(raw)
                operations.validate_type(row, "Work")
                count += 1
                b.require(
                    count <= MAX_WORKS and row["work_id"] == count,
                    "B2_RUNTIME_WORK_ORDER",
                )
                digest = b.sha(raw)
                if build:
                    self.offsets.append(offset)
                    self.hashes.extend(digest)
                else:
                    b.require(
                        count <= len(self.offsets)
                        and self.hashes[(count - 1) * 32 : count * 32] == digest,
                        "B2_RUNTIME_WORK_CHANGED",
                    )
                hasher.update(raw)
                yield row
            b.require(
                count == len(self.offsets) and hasher.hexdigest() == self.expected,
                "B2_RUNTIME_WORK_CHANGED",
            )
            self._assert_path()

    def _assert_path(self):
        io.private_directory(self.path.parent)
        info = self.path.stat(follow_symlinks=False)
        b.require(
            (info.st_dev, info.st_ino, info.st_size) == self.identity
            and stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and info.st_nlink == 1
            and info.st_mode & 0o077 == 0,
            "B2_RUNTIME_WORK_CHANGED",
        )

    def verify(self, *, build=False):
        first = True

        def factory():
            nonlocal first
            construction, first = build and first, False
            return self.rows(build=construction)

        operations.verify_work_manifest(factory, self.plan)

    def row(self, work_id):
        b.require(
            type(work_id) is int and 1 <= work_id <= len(self.offsets),
            "B2_RUNTIME_WORK_ORDER",
        )
        self.check()
        with self._open() as stream:
            stream.seek(self.offsets[work_id - 1])
            raw = stream.readline(MAX_WORK_BYTES + 1)
            b.require(
                b.sha(raw) == self.hashes[(work_id - 1) * 32 : work_id * 32],
                "B2_RUNTIME_WORK_CHANGED",
            )
            row = io.metadata(raw)
            b.require(row["work_id"] == work_id, "B2_RUNTIME_WORK_ORDER")
            self._assert_path()
            return row


class Authority:
    """A pinned local trust root; every grant is exact and re-read on use.

    Independently reviewed control-plane records may be added exclusively to
    grant_directory for facts only known after responses. This code never writes
    grants. Ownership/private modes are integrity controls, not proof of issuer
    competence; genuine source/delegation/review records are required inputs.
    """

    def __init__(self, records, digest, config, clock):
        self.records, self.digest, self.config, self.clock = (
            records,
            digest,
            config,
            clock,
        )
        self.port = None
        self.pending_nonsecret = set()
        self._runtime_inventory_checks = 0
        self._runtime_inventory_record_sha256 = None
        self._sampling_bound_record_sha256 = None
        self._enforcement_checks = 0
        self._enforcement_record_sha256 = None
        self._enforcement_lock = threading.Lock()
        self._ra_identity_checks = self._ra_read_calls = self._ra_read_bytes = 0
        self._root()

    def _root(self):
        root = io.metadata(self.records.raw(self.digest))
        fields = {
            "version",
            "scope_sha256",
            "population_scope",
            "owner_decision_sha256",
            "delegation_sha256",
            "review_sha256",
            "valid_from",
            "valid_until",
            "phase_authority_sha256",
            "phase_names",
            "grants",
            "grant_directory",
            "dynamic_purposes",
        }
        b.require(
            set(root) == fields
            and root["version"] == (RA_AUTHORITY_VERSION if self.config["runtime"]["version"] in (RA_VERSION,"stage12_development_runtime_lp1_ra_g1_v1") else AUTHORITY_VERSION)
            and root["population_scope"] == self.config["runtime"]["population_scope"]
            and root["scope_sha256"] == scope_hash(self.config),
            "B2_RUNTIME_AUTHORITY_SCOPE",
        )
        for name in (
            "owner_decision_sha256",
            "delegation_sha256",
            "review_sha256",
            "phase_authority_sha256",
        ):
            self.records.raw(root[name])
        b.validate_type(root["valid_from"], "Z")
        b.validate_type(root["valid_until"], "Z")
        b.require(
            root["valid_from"] <= self.clock.utc() < root["valid_until"],
            "B2_RUNTIME_AUTHORITY_EXPIRED",
        )
        b.require(
            type(root["phase_names"]) is list
            and self.config["runtime"]["phase"] in root["phase_names"]
            and len(root["phase_names"]) <= 11,
            "B2_RUNTIME_AUTHORITY_SCOPE",
        )
        b.require(
            type(root["grants"]) is list and len(root["grants"]) <= MAX_GRANTS,
            "B2_RUNTIME_GRANT_BOUND",
        )
        b.require(
            type(root["dynamic_purposes"]) is list
            and set(root["dynamic_purposes"]) <= {"dispatch", "nonsecret_record"},
            "B2_RUNTIME_AUTHORITY_SCOPE",
        )
        return root

    def require(self, purpose, digest, context):
        if self.port is not None and purpose in {
            "protected_input",
            "dispatch",
            "segment_open",
            "publication",
        }:
            self.port.verify_sampling_assurance(verify_inventory=purpose != "dispatch")
        b.validate_type(digest, "D")
        b.require(
            type(purpose) is str and type(context) is dict, "B2_RUNTIME_AUTHORITY_SCOPE"
        )
        if self.port is not None and self.port.local_only:
            if self.port.local_contract.local_authority_check(self.port, purpose, digest, context):
                return
        if self.port is not None and self.port.ra_enabled and purpose in {
            "resource_policy","resource_adoption","resource_selection","resource_technical_review",
            "resource_invocation_graph","resource_risk_inventory","owner_reported_project_approval","resource_registered_paths",
        }:
            self.records.raw(digest)
        root = self._root()
        if purpose == "dispatch" and self.port is not None and self.port.ra_enabled:
            self._resource_dispatch(context)
        if purpose.startswith("phase_"):
            b.require(
                purpose[6:] in root["phase_names"]
                and purpose[6:] == self.config["runtime"]["phase"]
                and digest == root["phase_authority_sha256"]
                and context
                == {
                    "configuration_sha256": b.digest(self.config),
                    "population_scope": root["population_scope"],
                },
                "B2_RUNTIME_AUTHORITY_SCOPE",
            )
            return
        if purpose == "nonsecret_record" and purpose in root["dynamic_purposes"]:
            b.require(
                context == {} and digest in self.pending_nonsecret,
                "B2_RUNTIME_UNCHECKED_RECORD",
            )
            return
        if purpose == "dispatch" and purpose in root["dynamic_purposes"]:
            b.require(
                self.port is not None
                and self.port.phase in DISPATCH
                and self.port.mode == "EXACT_AUTHORIZED_DISPATCH",
                "B2_RUNTIME_DISPATCH_UNISSUED",
            )
            profile, plan, start, _, _, works = (
                self.port._campaign
                if self.port._campaign is not None
                else self.port.campaign_inputs()
            )
            b.require(
                set(context) == {"work", "attempt", "state"}
                and digest == start["initial_workload_authority_sha256"]
                and type(context["attempt"]) is int
                and 1 <= context["attempt"] <= 5
                and context["state"] in profile["states"]
                and context["work"] == self.port.work.row(context["work"]["work_id"]),
                "B2_RUNTIME_AUTHORITY_SCOPE",
            )
            return
        if purpose == "permission_current":
            b.require(
                set(context) == {"permission", "now", "until"},
                "B2_RUNTIME_AUTHORITY_SCOPE",
            )
            now, until = context["now"], context["until"]
            b.require(
                root["valid_from"] <= now <= until < root["valid_until"],
                "B2_RUNTIME_AUTHORITY_EXPIRED",
            )
            context = {"permission": context["permission"], "until": until}
        expected = {
            "purpose": purpose,
            "evidence_sha256": digest,
            "context_sha256": b.digest(context),
        }
        for grant in root["grants"]:
            b.require(set(grant) == set(expected), "B2_RUNTIME_AUTHORITY_SCOPE")
            if grant == expected:
                return
        # Separate, immutable, exact post-outcome grant. No permissive default.
        directory = absolute(root["grant_directory"])
        io.private_directory(directory)
        grant_path = directory / (b.digest(expected) + ".json")
        grant = object_at(grant_path)
        b.require(
            set(grant)
            == {
                "version",
                "decision",
                "subject",
                "delegation_sha256",
                "review_record_sha256",
            }
            and grant["version"] == "stage12_runtime_exact_grant_v1"
            and grant["decision"] == "ISSUED"
            and grant["subject"] == expected
            and grant["delegation_sha256"] == root["delegation_sha256"],
            "B2_RUNTIME_AUTHORITY_SCOPE",
        )
        self.records.raw(grant["review_record_sha256"])

    def charge_enforcement_check(self, record):
        if self.port is not None:
            self.port.check_deadline()
        digest = b.digest(record)
        with self._enforcement_lock:
            b.require(
                self._enforcement_record_sha256 in (None, digest),
                "WF_AP2_EVIDENCE_CHANGED",
            )
            self._enforcement_record_sha256 = digest
            self._enforcement_checks += 1
            b.require(
                self._enforcement_checks <= record["maximum_enforcement_checks"],
                "WF_AP2_ENFORCEMENT_BUDGET",
            )

    def charge_runtime_inventory_check(self):
        b.require(
            self._sampling_bound_record_sha256 is not None, "WF_AP2_RUNTIME_BUDGET"
        )
        record = io.metadata(self.records.raw(self._sampling_bound_record_sha256))
        if record.get("method") == "LOGICAL_LIMITS_AND_SCOPED_MONITORING":
            self.charge_identity_check(record)
            return
        if self.port is not None:
            self.port.check_deadline()
        digest = b.digest(record)
        with self._enforcement_lock:
            b.require(
                self._runtime_inventory_record_sha256 in (None, digest),
                "WF_AP2_EVIDENCE_CHANGED",
            )
            self._runtime_inventory_record_sha256 = digest
            self._runtime_inventory_checks += 1
            b.require(
                self._runtime_inventory_checks
                <= (record["maximum_identity_checks"] if record.get("method") == "LOGICAL_LIMITS_AND_SCOPED_MONITORING" else record["maximum_runtime_inventory_checks"]),
                "WF_AP2_RUNTIME_BUDGET",
            )

    def sampling_bound(self, profile, start):
        contract = operations.for_profile(profile)
        value = io.metadata(self.records.raw(profile["sampling_runtime_bound_sha256"]))
        contract.validate_bound(
            value,
            profile,
            start,
            configuration_scope_sha256=self.configuration_scope_sha256,
        )
        self._sampling_bound_record_sha256 = profile["sampling_runtime_bound_sha256"]
        return value

    def charge_identity_check(self,record):
        with self._enforcement_lock:
            self._ra_identity_checks += 1
            b.require(self._ra_identity_checks <= record["maximum_identity_checks"],"B2_RA_IDENTITY_BUDGET")

    def initial_resource_facts(self,record):
        from . import s12_ra_g1_assurance as assurance
        facts=io.metadata(self.records.raw(record["initial_environment_observation_sha256"]))
        originals=io.metadata(self.records.raw(facts["observation_inventory_sha256"]))
        validate=getattr(assurance,"validate_environment_originals",None)
        b.require(callable(validate),"B2_RA_INITIAL_ORIGINALS_REQUIRED")
        validate(facts,originals)
        return facts

    def resource_facts(self,record):
        from . import s12_ra_g1_assurance as assurance
        if self.port._test is not None:
            provider=self.port._test.get("resource_facts")
            b.require(callable(provider),"B2_RA_CURRENT_FACTS_REQUIRED")
            return provider(record)
        facts,originals=assurance.observe_current_facts(check=self.port.check_deadline,
            read_charge=self.port.charge_ra_original_read)
        self.port.ra_current_environment_originals=originals
        return facts

    def resource_selection(self,record):
        return io.metadata(self.records.raw(record["selection_sha256"]))

    def capacity_observation(self,record):
        from . import s12_b2_ra_g1_resources as resources
        value=io.metadata(self.records.raw(self.port.settings["phase_capacity_observation_sha256"]))
        resources.validate_capacity_originals(value,self.records)
        return value

    def register_coordinator(self,coordinator):
        b.require(self.port is not None and self.port.ra_enabled and
                  getattr(self.port,"ra_coordinator",None) in (None,coordinator),"B2_RA_COORDINATOR_CHANGED")
        if getattr(self.port,"ra_coordinator",None) is coordinator:
            return
        snapshot=coordinator.ra_charged_snapshot
        b.require(type(snapshot) is tuple and len(snapshot) == 2,"B2_RA_COUNTER_ORIGINAL_REQUIRED")
        self.port.ra_coordinator=coordinator
        self.port.ra_coordinator_entry_snapshot=tuple(b.uint(x) for x in snapshot)
        self.port.ra_coordinator_entry_attempts=sum(snapshot)
        allocation={x["name"]:x["bytes"] for x in self.port.ra_binding["logical_allocations"]}
        b.require(allocation["OTHER_LOGICAL"] >= 1208*8,"B2_RA_LOGICAL_WORK_IDS")
        self._ra_work_ids=bytearray(1208*8)
        self._ra_work_counts=[0,0]

    def _resource_dispatch(self,context):
        import struct
        p=self.port
        coordinator=getattr(p,"ra_coordinator",None)
        b.require(coordinator is not None and set(context) == {"work","attempt","state"},"B2_RA_COUNTER_ORIGINAL_REQUIRED")
        current=tuple(coordinator.ra_charged_snapshot)
        entry=p.ra_coordinator_entry_snapshot
        kind=0 if context["work"]["kind"] == "DATA" else 1
        delta=[b.uint(current[i])-entry[i] for i in range(2)]
        b.require(all(x >= 0 for x in delta),"B2_RA_COUNTER_ORIGINAL_REQUIRED")
        delta[kind]+=1
        b.require(delta[0] <= 1800 and delta[1] <= 40 and sum(delta) <= min(1840,p.ra_selection["limits"]["attempts"]),"B2_RA_SEGMENT_ATTEMPT_LIMIT")
        member_prior=p.ra_prior_member_attempts.get(p.ra_current_member_id,0)
        root=p.ra_prior_root_attempts-member_prior+sum(current)+1
        b.require(root <= p.resource_model["limits"]["data_attempts"]+p.resource_model["limits"]["control_attempts"],"B2_RA_ROOT_ATTEMPT_LIMIT")
        work=b.uint(context["work"]["work_id"],True)
        offset=0 if kind == 0 else 1200
        count=self._ra_work_counts[kind]
        for index in range(count):
            if struct.unpack_from("<Q",self._ra_work_ids,(offset+index)*8)[0] == work:
                break
        else:
            b.require(count < (1200 if kind == 0 else 8),"B2_RA_SEGMENT_WORK_LIMIT")
            struct.pack_into("<Q",self._ra_work_ids,(offset+count)*8,work)
            self._ra_work_counts[kind]+=1

    def resource_prewrite(self,*,next_write_bytes,next_creations):
        from . import s12_b2_ra_g1_resources as resources
        return resources.runtime_prewrite(self.port,next_write_bytes=next_write_bytes,next_creations=next_creations)

    def enforcement_facts(self, record):
        from . import s12_wf_ap2_assurance as assurance

        if self.port is not None and self.port._test is not None:
            adapter = self.port._test.get("enforcement_facts")
            b.require(callable(adapter), "WF_AP2_ENFORCEMENT_REQUIRED")
            return adapter(record)
        return assurance.observe_linux_domain(record["domain"])

    def supported_size(self, digest):
        value = io.metadata(self.records.raw(digest))
        b.require(
            set(value)
            == {
                "version",
                "supported_size",
                "complete_required_matrix",
                "source_evidence_sha256",
                "review_sha256",
            }
            and value["version"] == "stage12_reviewed_size_capability_v1"
            and value["complete_required_matrix"] is True
            and type(value["supported_size"]) is int
            and 10 < value["supported_size"] <= 40,
            "B2_CAPABILITY_UNRESOLVED",
        )
        self.records.raw(value["source_evidence_sha256"])
        self.records.raw(value["review_sha256"])
        self.require("supported_size", digest, value)
        return value["supported_size"]


class PreparationGate:
    """Pre-window core DAG: exact scientific/input/privacy authority, no dispatch."""

    def __init__(self, port):
        self.port = port
        self.records, self.authority, self.scope = (
            port.records,
            port.authority,
            port.population_scope,
        )

    def check(self):
        p = self.port
        p.check_deadline()
        decision = self.records.get(
            p.settings["scientific_decision_sha256"], "scientific_decision"
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
        return evidence.privacy(
            self.records,
            p.settings["permission_sha256"],
            now=p.clock.utc(),
            until=p.phase_until,
            authority=self.authority,
            revocation=p.revocation,
        )

    def require(self, purpose, digest, context):
        b.require(
            purpose not in {"dispatch", "emission", "segment_open", "publication"},
            "B2_RUNTIME_DISPATCH_UNISSUED",
        )
        self.check()
        self.authority.require(purpose, digest, context)


class RuntimeRecords(evidence.Records):
    """Every new record gets the port's real secret check before authority use."""

    def __init__(self, root, port):
        super().__init__(root)
        self.port = port

    def raw(self,digest):
        if getattr(self.port,"ra_enabled",False):
            b.validate_type(digest,"D")
            path=self.root/(digest+".json")
            size=path.stat(follow_symlinks=False).st_size
            self.port.charge_ra_original_read(1,size+1)
        return super().raw(digest)

    def put(self, raw, *, owner, secret_guard):
        self.port.check_deadline()
        self.port.secret_guard(raw)
        digest = b.sha(raw).hex()
        pending = self.port.authority.pending_nonsecret
        b.require(len(pending) < MAX_GRANTS, "B2_RUNTIME_GRANT_BOUND")
        pending.add(digest)
        path = self.root / (digest + ".json")
        existed = path.exists()
        try:
            ledger = self.port.resource_ledger
            if (
                not existed
                and ledger is not None
                and callable(getattr(ledger, "reserve_record", None))
            ):
                ledger.reserve_record(path, digest, size=len(raw))
            value = super().put(raw, owner=owner, secret_guard=secret_guard)
            self.port.check_deadline()
            if not existed:
                info = path.stat(follow_symlinks=False)
                self.port._record_generated_bytes += max(
                    info.st_size, info.st_blocks * 512
                )
                self.port._record_generated_files += 1
            return value
        finally:
            pending.discard(digest)


class ExactControl:
    """Explicit reviewed byte-hash control; no DATA projection or state attestation."""

    def __init__(self, record, recipe):
        b.require(
            set(record)
            == {
                "version",
                "recipe_sha256",
                "implementation_contract_sha256",
                "target_ascii",
                "accepted_payload_sha256",
            }
            and record["version"] == "stage12_runtime_exact_control_v1"
            and record["recipe_sha256"] == recipe["recipe_sha256"]
            and record["implementation_contract_sha256"]
            == recipe["implementation_contract_sha256"],
            "B2_CONTROL_ADAPTER_REQUIRED",
        )
        b.require(
            type(record["target_ascii"]) is str
            and record["target_ascii"].startswith("/")
            and not record["target_ascii"].startswith("//")
            and record["target_ascii"].isascii()
            and not any(ord(x) <= 32 or ord(x) == 127 for x in record["target_ascii"]),
            "B2_CONTROL_ADAPTER_REQUIRED",
        )
        b.require(
            type(record["accepted_payload_sha256"]) is list
            and 0 < len(record["accepted_payload_sha256"]) <= 16,
            "B2_CONTROL_ADAPTER_REQUIRED",
        )
        for h in record["accepted_payload_sha256"]:
            b.validate_type(h, "D")
        self.record, self.recipe = record, recipe

    def target(self, recipe):
        b.require(recipe == self.recipe, "B2_CONTROL_ADAPTER_REQUIRED")
        return self.record["target_ascii"].encode("ascii")

    def validate(self, recipe, raw):
        self.target(recipe)
        h = b.sha(raw).hex()
        b.require(
            h in self.record["accepted_payload_sha256"], "RESPONSE_CONTRACT_INVALID"
        )
        return b.canonical(
            {
                "version": "stage12_runtime_control_receipt_v1",
                "recipe_sha256": recipe["recipe_sha256"],
                "response_sha256": h,
                "service_state_verified": False,
            }
        )


class RuntimePort:
    population_scope = b.DEVELOPMENT
    test_only = False

    def __init__(self, config, *, _test=None,resource_role_entry_ns=None):
        direct_entry_ns=_test["clock"].now_ns() if _test is not None else time.monotonic_ns()
        try:
            self._initialize(config,_test=_test,resource_role_entry_ns=resource_role_entry_ns,
                direct_entry_ns=direct_entry_ns)
        except BaseException:
            if not getattr(self,"ra_enabled",False):
                raise
            setup=getattr(self,"ra_setup_session",None)
            if setup is not None:
                try:
                    setup.abort()
                except BaseException:
                    pass
            guard=getattr(self,"offline_guard",None)
            if guard is not None:
                try:
                    guard.close()
                except BaseException:
                    pass
            raise

    def _initialize(self, config, *, _test=None,resource_role_entry_ns=None,direct_entry_ns=None):
        self.config, self.settings = config, config["runtime"]
        r = self.settings
        self.ra_enabled = r.get("version") in (RA_VERSION,"stage12_development_runtime_lp1_ra_g1_v1")
        if self.ra_enabled:
            b.require(type(direct_entry_ns) is int and 0 <= direct_entry_ns <= (_test["clock"].now_ns() if _test is not None else time.monotonic_ns()),
                      "B2_RA_ROLE_ENTRY_REQUIRED")
            if _test is None:
                b.require(type(resource_role_entry_ns) is int and 0 < resource_role_entry_ns <= direct_entry_ns,
                          "B2_RA_ROLE_ENTRY_REQUIRED")
            elif resource_role_entry_ns is None:
                resource_role_entry_ns=direct_entry_ns
            self.ra_role_entry_ns=resource_role_entry_ns
        self.local_contract=local
        if self.ra_enabled:
            from . import s12_b2_ra_g1_local as ra_local
            from . import s12_b2_ra_g1_contract as ra_contract
            self.local_contract=ra_local
            ra_contract.validate_configuration(config)
        else:
            b.require(config.get("schema_version") != "stage12_development_sampling_configuration_b2_ap_ra_g1_v1","B2_RA_MIXED_METHOD")
        self.local_only = r.get("version") == self.local_contract.RUNTIME_VERSION
        runtime_fields = (RUNTIME_FIELDS - RA_REPLACED) | RA_FIELDS if self.ra_enabled else RUNTIME_FIELDS
        self.resource_binding = r.get("resource_retention")
        successor_fields = (
            {"resource_retention"} if self.resource_binding is not None else set()
        )
        b.require(
            set(r)
            == (
                runtime_fields | self.local_contract.EXTRA_FIELDS
                if self.local_only
                else runtime_fields
            )
            | successor_fields
            and r["version"] == (self.local_contract.RUNTIME_VERSION if self.local_only else RA_VERSION if self.ra_enabled else VERSION),
            "B2_RUNTIME_CONFIG",
        )
        if self.local_only:
            self.local_contract.validate_config(config)
        if self.resource_binding is not None:
            from . import s12_b2_resources as resources

            binding = dict(self.resource_binding)
            if "allocation_limits_sha256" in binding:
                b.validate_type(binding.pop("allocation_limits_sha256"), "D")
            if "slot_binding_sha256" in binding:
                b.validate_type(binding.pop("slot_binding_sha256"), "D")
            resources.shape(binding, resources.RUNTIME_BINDING_SCHEMA)
        b.require(
            r["mode"] in ("OFFLINE_ONLY", "EXACT_AUTHORIZED_DISPATCH"),
            "B2_RUNTIME_CONFIG",
        )
        self.mode, self.phase = r["mode"], r["phase"]
        from ..stage12_development_cli import PHASES

        b.require(
            self.phase in PHASES
            and (
                self.local_only
                or self.phase not in ("build-workload", "offline-preflight")
            ),
            "B2_PHASE_INVALID",
        )
        if _test is None:
            b.require(r["population_scope"] == b.DEVELOPMENT, "B2_POPULATION_SCOPE")
            from ...execution_policy import require_goethe_nhr_slurm

            require_goethe_nhr_slurm("stage12 reviewed DEVELOPMENT runtime")
            self.clock = Clock()
        else:
            b.require(r["population_scope"] == b.SYNTHETIC, "B2_POPULATION_SCOPE")
            self.population_scope, self.test_only = b.SYNTHETIC, True
            self.clock = _test["clock"]
        b.require(
            self.phase not in DISPATCH or self.mode == "EXACT_AUTHORIZED_DISPATCH",
            "B2_RUNTIME_DISPATCH_UNISSUED",
        )
        self._stack, self._closed = ExitStack(), False
        self._key = None
        self.offline_guard = None
        self._local_context = None
        self.work = None
        self._campaign = None
        self._sampling_runtime_inventory_sha256 = None
        self._reader = None
        self._catalog = None
        self.resource_ledger = None
        self.resource_model = None
        self.resource_command = None
        self.resource_command_deadline = None
        self.allocation_limits = None
        self._test = _test
        self._generation_roots = None
        self._checking_generation = False
        self._record_generated_bytes = self._record_generated_files = 0
        for k in (("phase_duration_ms","phase_logical_write_ceiling_bytes","phase_generation_max_files","phase_generation_check_ms") if self.ra_enabled else (
            "phase_duration_ms",
            "phase_memory_bytes",
            "phase_disk_capacity_bytes",
            "phase_generation_bound_bytes",
            "phase_generation_max_files",
            "phase_generation_check_ms",
        )):
            b.uint(r[k], True)
        b.require(
            (self.ra_enabled or r["phase_generation_bound_bytes"] <= r["phase_disk_capacity_bytes"])
            and r["phase_generation_check_ms"] <= r["phase_duration_ms"],
            "B2_RUNTIME_GENERATION_BOUND",
        )
        self.started_ns = self.ra_role_entry_ns if self.ra_enabled else self.clock.now_ns()
        b.require(not self.ra_enabled or type(self.started_ns) is int and 0<=self.started_ns <= self.clock.now_ns(),
                  "B2_RA_ROLE_ENTRY_REQUIRED")
        self._last_generation_check = self.started_ns
        self.deadline = self.started_ns + r["phase_duration_ms"] * 1000000
        b.validate_type(r["phase_until"], "Z")
        self.phase_until = r["phase_until"]
        b.require(self.clock.utc() < self.phase_until, "B2_RUNTIME_DEADLINE")
        self.ra_original_read_calls = self.ra_original_read_bytes = 0
        self.ra_coordinator = None
        self.records = RuntimeRecords(absolute(r["records_root"]), self)
        self.authority = Authority(
            self.records, r["authority_sha256"], config, self.clock
        )
        self.authority.port = self
        self.ra_binding_sha256 = None
        self.ra_binding = None
        self.ra_selection = None
        self.ra_monitor = None
        if self.ra_enabled:
            from . import s12_b2_ra_g1_resources as ra_resources
            ra_resources.prepare_runtime(self)
        self._source_check()
        if self.local_only:
            self.gate = self.local_contract.Gate(self)
        elif self.phase in PREPARATION:
            b.require(
                self.mode == "OFFLINE_ONLY"
                and r["gate"] is None
                and r["campaign"] is None,
                "B2_RUNTIME_PREPARATION_SCOPE",
            )
            self.gate = PreparationGate(self)
        else:
            b.require(
                type(r["gate"]) is dict and set(r["gate"]) == _GATE_FIELDS,
                "B2_RUNTIME_GATE",
            )
            self.gate = evidence.Gate(
                self.records,
                self.authority,
                population_scope=self.population_scope,
                clock=self.clock,
                revocation=self.revocation,
                window_state=self.window_state,
                **r["gate"],
            )
        self.control_adapters = {}
        self.response_rules = None
        self.runtime_inventory = None
        self.predecessor = None
        self.segment = None
        self.output = self.scratch = None
        if self.mode == "OFFLINE_ONLY":
            guard = OfflineGuard()
            self.offline_guard = self.local_contract.Denial(guard) if self.local_only else guard
            if not self.local_only:
                self._stack.callback(self.offline_guard.close)
        if self.ra_enabled:
            ra_resources.finish_protected_setup(self)

    def check_resource_deadline(self):
        # The source-owned resource suffix continues after scientific readers
        # close. It cannot reopen a closed port or grant dispatch/input access.
        now=self.clock.now_ns()
        b.require(self.ra_enabled and not getattr(self,"ra_resource_finalized",False) and
                  (getattr(self,"ra_active_scope_deadline",None) is None or now < self.ra_active_scope_deadline) and
                  now < self.deadline and (self.resource_command_deadline is None or now < self.resource_command_deadline) and
                  self.clock.utc() < self.phase_until and
                  (self.ra_binding is None or self.ra_binding["valid_from"] <= self.clock.utc() < self.ra_binding["valid_until"]),"B2_RA_RESOURCE_DEADLINE")

    def resource_monitor_counters(self):
        from . import s12_b2_ra_g1_resources as resources
        return resources.monitor_counters(self)

    def charge_ra_original_read(self,calls,size):
        if not getattr(self,"ra_enabled",False):
            return
        self.ra_original_read_calls+=b.uint(calls)
        self.ra_original_read_bytes+=b.uint(size)
        binding=getattr(self,"ra_binding",None)
        if binding is not None:
            b.require(self.ra_original_read_calls <= binding["maximum_original_read_calls"] and
                      self.ra_original_read_bytes <= binding["maximum_original_read_bytes"],"B2_RA_ORIGINAL_READ_BUDGET")

    def _source_check(self):
        self.check_deadline()
        r = self.settings
        b.require(
            type(r["source_files"]) is list and 0 < len(r["source_files"]) <= 512,
            "B2_RUNTIME_SOURCE_BOUND",
        )
        root = absolute(r["source_root"])
        seen = set()
        for entry in r["source_files"]:
            self.check_deadline()
            b.require(
                set(entry) == {"path", "sha256"} and entry["path"] not in seen,
                "B2_RUNTIME_SOURCE_BOUND",
            )
            seen.add(entry["path"])
            rel = Path(entry["path"])
            b.require(
                not rel.is_absolute() and ".." not in rel.parts, "B2_RUNTIME_PATH"
            )
            # Repository sources are not controlled data and need not be0600.
            p = root / rel
            b.require(not p.is_symlink() and p.is_file(), "B2_RUNTIME_INPUT_CHANGED")
            if getattr(self,"ra_enabled",False):
                from . import s12_b2_ra_g1_resources as resources
                h=resources.bounded_source_digest(self,p,self.check_deadline)
            else:
                with p.open("rb") as f:
                    h = hashlib.file_digest(f, "sha256").hexdigest()
            b.require(h == entry["sha256"], "B2_RUNTIME_INPUT_CHANGED")

    def check_deadline(self):
        now = self.clock.now_ns()
        b.require(
            not self._closed
            and now < self.deadline
            and (not self.ra_enabled or getattr(self,"ra_active_scope_deadline",None) is None or now < self.ra_active_scope_deadline)
            and (
                self.resource_command_deadline is None
                or now < self.resource_command_deadline
            )
            and self.clock.utc() < self.phase_until,
            "B2_RUNTIME_DEADLINE",
        )
        if self.ra_enabled:
            if getattr(self,"ra_selection",None) is not None:
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                used = peak if sys.platform == "darwin" else peak * 1024
                b.require(used <= self.ra_selection["monitor"]["self_rss_stop_bytes"],"B2_RA_SELF_RSS_STOP")
        else:
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            used = peak if sys.platform == "darwin" else peak * 1024
            b.require(
                used <= self.settings["phase_memory_bytes"]
                and (
                    self.resource_command is None
                    or used <= self.resource_command["max_memory_bytes"]
                ),
                "B2_RUNTIME_MEMORY_LIMIT",
            )
        if (
            not self.ra_enabled
            and (
                self.local_only
                or self.phase in PREPARATION
                or self.resource_command is not None
            )
            and self._generation_roots is not None
            and not self._checking_generation
            and self.clock.now_ns() - self._last_generation_check
            >= self.settings["phase_generation_check_ms"] * 1000000
        ):
            self.reconcile_generation()

    def bind_session(self, phase, config, output, scratch, authority_hash):
        b.require(
            phase == self.phase and config == self.config, "B2_RUNTIME_PHASE_SCOPE"
        )
        b.require(_PHASE_LOCK.acquire(blocking=False), "B2_RUNTIME_PHASE_BUSY")
        self._stack.callback(_PHASE_LOCK.release)
        # Library-created SQLite/DuckDB/Arrow scratch must be private while
        # open, not only after final writers normalize modes. This process-
        # global setting is scoped by the already exclusive phase lock.
        prior_umask = os.umask(0o077)
        self._stack.callback(os.umask, prior_umask)
        try:
            self._bind_session_owned(phase, config, output, scratch, authority_hash)
        except BaseException:
            try:
                self._stack.close()
            except BaseException:
                pass  # Preserve the initiating bind failure.
            if self.local_only and self.offline_guard is not None:
                self.offline_guard.close()
            self._key = None
            self._closed = True
            raise

    def _bind_session_owned(self, phase, config, output, scratch, authority_hash):
        self.output = under(output, self.settings["output_parent"])
        self.scratch = under(scratch, self.settings["scratch_parent"])
        if (
            self.resource_binding is not None
            and "slot_binding_sha256" in self.resource_binding
        ):
            paths = config.get("command_paths")
            b.require(
                type(paths) is dict
                and set(paths) == {"output_path", "scratch_path"}
                and absolute(paths["output_path"]) == self.output
                and absolute(paths["scratch_path"]) == self.scratch,
                "B2_GRAPH_COMMAND_PATHS",
            )
        b.require(
            self.output != self.scratch
            and not self.output.is_relative_to(self.scratch)
            and not self.scratch.is_relative_to(self.output),
            "B2_RUNTIME_PATH",
        )
        self.authority.require(
            "phase_" + phase,
            authority_hash,
            {
                "configuration_sha256": b.digest(config),
                "population_scope": self.population_scope,
            },
        )
        self.check_deadline()
        if self.local_only:
            self.gate.check()
        self.authority.require(
            "resources",
            self.settings["resource_evidence_sha256"],
            {
                k: self.settings[k]
                for k in (("phase_duration_ms","phase_monitor_selection_sha256","phase_capacity_observation_sha256",
                           "phase_logical_write_ceiling_bytes","phase_generation_max_files","phase_generation_check_ms",
                           "temporary_root","output_parent","scratch_parent") if self.ra_enabled else (
                    "phase_duration_ms","phase_memory_bytes","phase_disk_capacity_bytes","phase_generation_bound_bytes",
                    "phase_generation_max_files","phase_generation_check_ms","temporary_root","output_parent","scratch_parent"))
            },
        )
        if not self.test_only:
            mem = os.environ.get("SLURM_MEM_PER_NODE")
            b.require(
                mem is not None
                and int(mem) * 2**20 >= (6*2**30 if self.ra_enabled else self.settings["phase_memory_bytes"]),
                "B2_RUNTIME_MEMORY_ALLOCATION",
            )
        if self.ra_enabled:
            self.authority.resource_prewrite(next_write_bytes=0,next_creations=0)
        else:
            b.require(self.free_bytes() >= self.settings["phase_disk_capacity_bytes"],"B2_RUNTIME_DISK_UNAVAILABLE")
        # Every generated namespace is exclusive and fresh. The input catalog,
        # source evidence and earlier phase outputs are not relabelled as new.
        temporary = under(
            self.settings["temporary_root"], self.settings["scratch_parent"]
        )
        roots = (
            self.output,
            self.output.with_name(self.output.name + ".identity.json"),
            self.scratch,
            self.scratch.with_name(self.scratch.name + "_readers"),
            self.scratch.with_name(self.scratch.name + "_runtime_reader"),
            temporary,
            *(
                (
                    Path(self.settings["window_state_path"]).parent
                    / (self.gate.window_hash + "_CLOSED.json"),
                )
                if self.phase == "close-window"
                and self.resource_binding is not None
                and "slot_binding_sha256" in self.resource_binding
                else ()
            ),
            *(
                (self.output.parent / (self.output.name + "_telemetry"),)
                if self.settings.get("campaign") is not None
                and getattr(
                    operations.for_profile(
                        self._profile_plan(self.settings["campaign"])[0]
                    ),
                    "AP_ENABLED",
                    False,
                )
                else ()
            ),
        )
        b.require(
            all(not p.exists() and not p.is_symlink() for p in roots)
            and len(set(roots)) == len(roots),
            "B2_RUNTIME_GENERATION_EXISTS",
        )
        b.require(
            all(not x.is_relative_to(y) for x in roots for y in roots if x != y),
            "B2_RUNTIME_PATH",
        )
        self.verify_sampling_assurance()
        self._bind_resource_command()
        self._generation_roots = roots
        b.require(not self._generation_paths(), "B2_RUNTIME_GENERATION_EXISTS")
        io.reserve(temporary)
        # SQLite temp files and Python temp files stay in the same accounted
        # private namespace. One CLI phase owns this process and global setting.
        if self.allocation_limits is not None:
            self.allocation_limits.claim("SQLITE")
        db = sqlite3.connect(":memory:")
        self._stack.callback(db.close)
        previous = db.execute("pragma temp_store_directory").fetchone()

        def set_temp(path):
            db.execute(
                "pragma temp_store_directory='" + str(path).replace("'", "''") + "'"
            )

        prior_python_temp = tempfile.tempdir

        def restore_temp():
            try:
                set_temp(previous[0] if previous else "")
            finally:
                tempfile.tempdir = prior_python_temp
                db.close()

        self._stack.callback(restore_temp)
        set_temp(temporary)
        b.require(
            db.execute("pragma temp_store_directory").fetchone() == (str(temporary),),
            "B2_RUNTIME_TEMP_DIRECTORY",
        )
        tempfile.tempdir = str(temporary)
        self._stack.enter_context(
            inventory.ordering_scope(temporary, self.observe_ordering)
        )
        self._stack.enter_context(io.cooperative_io(self.check_deadline))
        if self.phase in {
            "preflight",
            "run-campaign",
            "run-direct-n",
            "close-campaign",
            "publish",
            "reopen",
        }:
            self.campaign_inputs()
        elif self.phase == "evaluate-calibration":
            b.require(self.settings["campaign"] is None, "B2_RUNTIME_CAMPAIGN")
            self._rules()
        elif self.phase == "close-window":
            b.require(self.settings["campaign"] is None, "B2_RUNTIME_CAMPAIGN")
        elif self.phase == "prepare-bootstrap":
            b.require(
                self.mode == "OFFLINE_ONLY" and self.settings["campaign"] is None,
                "B2_RUNTIME_DISPATCH_UNISSUED",
            )

    def revocation(self, permission_hash, now):
        x = object_at(self.settings["permission_current_path"])
        b.require(
            set(x)
            == {
                "version",
                "permission_sha256",
                "state",
                "valid_from",
                "valid_until",
                "evidence_sha256",
            }
            and x["version"] == "stage12_permission_current_v1"
            and x["permission_sha256"] == permission_hash
            and x["state"] == "CURRENT"
            and x["valid_from"] <= now < x["valid_until"],
            "PERMISSION_REVOKED",
        )
        return x["evidence_sha256"]

    def observe_ordering(self, force=False):
        """Physical ordering spill checks in ALL phases, including reopen.

        Ordinary checks respect the selected interval. Creation/pre-commit/
        pre-cleanup boundaries force an in-lifetime observation so linked DBs
        and rollback journals cannot vanish before accounting sees them.
        """
        self.check_deadline()
        if self.ra_enabled:
            return self.authority.resource_prewrite(next_write_bytes=0,next_creations=0)
        if (
            force
            or self.clock.now_ns() - self._last_generation_check
            >= self.settings["phase_generation_check_ms"] * 1_000_000
        ):
            return self.reconcile_generation()
        return None

    def reconcile_generation(self):
        """Bounded original filesystem accounting; never a physical reservation.

        Preparation checks occur only at the selected bounded interval and on
        successful phase exit. Capture retains its existing per-attempt hard
        admission accounting; this scan is not inserted into its hot path.
        A failing check preserves partial files and cannot return phase success.
        """
        if self._generation_roots is None:
            return
        self._checking_generation = True
        total, files = self._record_generated_bytes, self._record_generated_files
        try:

            def visit(path, depth=0):
                nonlocal total, files
                self.check_deadline()
                b.require(depth <= 64, "B2_RUNTIME_GENERATION_BOUND")
                info = path.stat(follow_symlinks=False)
                b.require(
                    info.st_uid == os.getuid()
                    and info.st_mode & 0o077 == 0
                    and not stat.S_ISLNK(info.st_mode),
                    "B2_RUNTIME_GENERATION_PATH",
                )
                files += 1
                total += max(info.st_size, info.st_blocks * 512)
                b.require(
                    files <= self.settings["phase_generation_max_files"]
                    and (self.ra_enabled or total <= self.settings["phase_generation_bound_bytes"]),
                    "B2_RUNTIME_GENERATION_BOUND",
                )
                if stat.S_ISDIR(info.st_mode):
                    with os.scandir(path) as entries:
                        for entry in entries:
                            visit(Path(entry.path), depth + 1)
                else:
                    b.require(
                        stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        "B2_RUNTIME_GENERATION_PATH",
                    )

            for root in self._generation_paths():
                visit(root)
            # SQLite/TemporaryFile spill can be unlinked while still consuming
            # storage. Conservatively include every live unlinked regular file
            # in this single-phase process; no file contents or paths are read.
            fd_root = (
                Path("/proc/self/fd")
                if sys.platform.startswith("linux")
                else Path("/dev/fd")
            )
            seen = set()
            with os.scandir(fd_root) as entries:
                for i, entry in enumerate(entries, 1):
                    b.require(
                        i <= self.settings["phase_generation_max_files"],
                        "B2_RUNTIME_GENERATION_BOUND",
                    )
                    try:
                        info = os.fstat(int(entry.name))
                    except (OSError, ValueError):
                        continue
                    if (
                        stat.S_ISREG(info.st_mode)
                        and info.st_nlink == 0
                        and (info.st_dev, info.st_ino) not in seen
                    ):
                        seen.add((info.st_dev, info.st_ino))
                        files += 1
                        total += max(info.st_size, info.st_blocks * 512)
                        b.require(
                            files <= self.settings["phase_generation_max_files"]
                            and (self.ra_enabled or total <= self.settings["phase_generation_bound_bytes"]),
                            "B2_RUNTIME_GENERATION_BOUND",
                        )
            if self.resource_command is not None and not self.ra_enabled:
                b.require(
                    total <= self.resource_command["max_generated_bytes"]
                    and files <= self.resource_command["max_generated_inodes"],
                    "B2_RS1_COMMAND_BOUND",
                )
            self._last_generation_check = self.clock.now_ns()
            return {"bytes": total, "entries": files}
        finally:
            self._checking_generation = False

    def _generation_paths(self):
        # Include SQLite -journal/-wal/-shm and the existing algorithms' named
        # reopen/index siblings. These namespaces must be empty at phase open.
        found = set()
        for root in self._generation_roots:
            with os.scandir(root.parent) as entries:
                for i, entry in enumerate(entries, 1):
                    b.require(
                        i <= self.settings["phase_generation_max_files"],
                        "B2_RUNTIME_GENERATION_BOUND",
                    )
                    if (
                        entry.name == root.name
                        or entry.name.startswith(root.name + "-")
                        or entry.name.startswith(root.name + "_")
                    ):
                        found.add(Path(entry.path))
                        b.require(
                            len(found) <= self.settings["phase_generation_max_files"],
                            "B2_RUNTIME_GENERATION_BOUND",
                        )
        return sorted(
            p for p in found if not any(p != q and p.is_relative_to(q) for q in found)
        )

    def window_state(self, window_hash):
        marker = Path(self.settings["window_state_path"]).parent / (
            window_hash + "_CLOSED.json"
        )
        if marker.exists():
            closed = object_at(marker)
            b.require(
                set(closed) == {"window_plan_sha256", "closure_sha256"}
                and closed["window_plan_sha256"] == window_hash,
                "WINDOW_CLOSED",
            )
            self.records.raw(closed["closure_sha256"])
            return {"state": "CLOSED", "evidence_sha256": closed["closure_sha256"]}
        x = object_at(self.settings["window_state_path"])
        b.require(
            set(x) == {"version", "window_plan_sha256", "state", "evidence_sha256"}
            and x["version"] == "stage12_window_runtime_state_v1"
            and x["window_plan_sha256"] == window_hash
            and x["state"] in ("OPEN", "CLOSED", "INTERRUPTED"),
            "WINDOW_CLOSED",
        )
        return {"state": x["state"], "evidence_sha256": x["evidence_sha256"]}

    def register_closed_window(self, closure_hash):
        # Closing authority registry is separate from the campaign writer.
        self.authority.require(
            "register_closed_window",
            closure_hash,
            {"window_plan_sha256": self.gate.window_hash},
        )
        path = Path(self.settings["window_state_path"]).parent / (
            self.gate.window_hash + "_CLOSED.json"
        )
        io.write(
            path,
            b.canonical(
                {
                    "window_plan_sha256": self.gate.window_hash,
                    "closure_sha256": closure_hash,
                }
            ),
        )
        info = path.stat(follow_symlinks=False)
        self._record_generated_bytes += max(info.st_size, info.st_blocks * 512)
        self._record_generated_files += 1
        self.gate.closed = True

    def assert_administrative_owner(self):
        self.check_deadline()
        self.authority.require(
            "administrative_writer",
            self.settings["administration_owner_sha256"],
            {
                "phase": self.phase,
                "configuration_scope_sha256": scope_hash(self.config),
            },
        )

    def secret_guard(self, raw):
        b.require(
            type(raw) is bytes and len(raw) <= b.MAX_METADATA, "B2_METADATA_LIMIT"
        )
        if self._key is not None:
            response.secret_guard(raw, self._key.value)
        # Offline generation is metadata-only and may not contain credential fields.
        lower = raw.lower()
        b.require(
            not any(
                token in lower
                for token in (
                    b"x-api-key",
                    b"authorization:",
                    b"bearer ",
                    b"api_key",
                    b"password",
                    b"private key",
                )
            ),
            "SECRET_ECHO_DETECTED",
        )

    def runtime_key(self):
        b.require(
            self.mode == "EXACT_AUTHORIZED_DISPATCH" and self.phase in DISPATCH,
            "B2_RUNTIME_PROVIDER_UNAUTHORIZED",
        )
        self.gate.before_dispatch()
        self._transport_profile()
        if self._key is None:
            if self.test_only:
                self._key = self._test["key_provider"]()
            else:
                b.require(
                    os.environ.get("SAFE_PELIAS_API_KEY_FILE")
                    == str(Path.home() / ".config/safe-geocoding/pelias_api_key")
                    and not os.environ.get("SAFE_PELIAS_API_KEY"),
                    "B2_RUNTIME_PROVIDER_UNAUTHORIZED",
                )
                self._key = transport.Secret.runtime()
        return self._key.value

    def free_bytes(self):
        self.check_deadline()
        p = (
            self.output.parent
            if self.output
            else absolute(self.settings["output_parent"])
        )
        st = os.statvfs(p)
        return st.f_bavail * st.f_frsize

    def campaign_inputs(self):
        self.check_deadline()
        spec = self.settings["campaign"]
        b.require(
            type(spec) is dict
            and set(spec)
            == {
                "profile_sha256",
                "plan_sha256",
                "start_sha256",
                "scientific_start_sha256",
                "admission_sha256",
                "work_path",
                "work_file_sha256",
                "segment_path",
                "predecessor_path",
                "runtime_inventory_sha256",
                "pause_after_ms",
                "control_adapters",
            },
            "B2_RUNTIME_CAMPAIGN",
        )
        profile, plan = RuntimePort._profile_plan(self, spec)
        start = operations.parse_selected(self.records.raw(spec["start_sha256"]))
        self.verify_sampling_assurance()
        science = self.records.get(
            spec["scientific_start_sha256"], "campaign_provenance"
        )
        admission = self.records.get(spec["admission_sha256"], "segment_admission")
        operations.validate_plan(plan, profile)
        if self.ra_enabled:
            b.require(getattr(operations.for_profile(profile),"RA_ENABLED",False) and
                      profile["resources"]["resource_selection_sha256"] == self.settings["phase_monitor_selection_sha256"] and
                      profile["resources"]["task_logical_write_ceiling_bytes"] >= plan["budgets"]["storage_bytes"],"B2_RA_CAMPAIGN_SELECTION")
        else:
            b.require(
                profile["resources"]["job_memory_bytes"]
                <= self.settings["phase_memory_bytes"]
                and plan["budgets"]["storage_bytes"]
                <= self.settings["phase_disk_capacity_bytes"],
                "B2_RUNTIME_CAMPAIGN_CAPACITY",
            )
        b.require(
            plan["population_scope"] == self.population_scope, "B2_POPULATION_SCOPE"
        )
        if self.work is None:
            self.work = WorkFile(
                absolute(spec["work_path"]),
                spec["work_file_sha256"],
                plan,
                self.check_deadline,
            )
        actual_inventory = self._actual_runtime_inventory()
        self.runtime_inventory = io.metadata(
            self.records.raw(spec["runtime_inventory_sha256"])
        )
        b.require(self.runtime_inventory == actual_inventory, "B2_RUNTIME_INVENTORY")
        if "resource_retention_model" in profile:
            from . import s12_b2_resources as resources
            if self.ra_enabled:
                from . import s12_b2_ra_g1_resources as resources

            model = profile["resource_retention_model"]
            b.require(
                self.resource_ledger is not None
                and self.resource_model == model
                and self.resource_binding["model_sha256"] == b.digest(model),
                "B2_RS1_COMMAND_BINDING",
            )
            resources.validate_plan_model(model, plan)
        else:
            b.require(
                self.resource_ledger is None and self.resource_model is None,
                "B2_RS1_COMMAND_BINDING",
            )
        b.uint(spec["pause_after_ms"], True)
        b.require(
            spec["pause_after_ms"]
            <= self.settings["phase_duration_ms"] - plan["shutdown_reserve_ms"],
            "B2_RUNTIME_SHUTDOWN_RESERVE",
        )
        b.require(
            type(spec["control_adapters"]) is dict
            and set(spec["control_adapters"])
            == {str(x["recipe_id"]) for x in plan["control_recipes"]},
            "B2_CONTROL_ADAPTER_REQUIRED",
        )
        self.control_adapters = {
            x["recipe_id"]: ExactControl(
                io.metadata(
                    self.records.raw(spec["control_adapters"][str(x["recipe_id"])])
                ),
                x,
            )
            for x in plan["control_recipes"]
        }
        self.segment = absolute(spec["segment_path"])
        self.predecessor = (
            None
            if spec["predecessor_path"] is None
            else absolute(spec["predecessor_path"])
        )
        if self.phase in DISPATCH:
            b.require(self.segment == self.output, "B2_RUNTIME_SEGMENT_SCOPE")
        self._campaign = (profile, plan, start, science, admission, self.work.rows)
        self._rules()
        return self._campaign

    def _ra_backend_digest(self,name,path,check):
        from . import s12_b2_ra_g1_resources as resources
        b.require(name in ("_hashlib","_ssl","_sqlite3","_duckdb","pyarrow.lib"),"B2_RA_BACKEND_SOURCE")
        return resources.bounded_source_digest(self,Path(path),check)

    def _actual_runtime_inventory(self, *, successor=None):
        value = {
            "version": "stage12_development_runtime_inventory_v1",
            "population_scope": self.population_scope,
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "source_inventory_sha256": b.digest(self.settings["source_files"]),
            "continuous_service_state": "NOT_VERIFIED",
            "resource_sampling_is_service_monitoring": False,
            "scientific_identity_verified": False,
        }
        if successor is None:
            spec = self.settings.get("campaign")
            if (
                spec is None
                and hasattr(self, "config")
                and self.settings.get("phase") == "prepare-bootstrap"
            ):
                spec = self.config.get("bootstrap")
            successor = bool(
                type(spec) is dict
                and hasattr(self, "records")
                and getattr(
                    operations.for_profile(
                        operations.parse_selected(
                            self.records.raw(spec["profile_sha256"])
                        )
                    ),
                    "AP_ENABLED",
                    False,
                )
            )
        if successor:
            from . import s12_wf_ap2_assurance as assurance
            if getattr(self,"ra_enabled",False):
                from . import s12_ra_g1_assurance as assurance

            if hasattr(self, "authority"):
                self.authority.charge_runtime_inventory_check()
            value.update(
                version="stage12_development_runtime_inventory_v2",
                wf_ap2_runtime_facts=assurance.runtime_facts(
                    check=getattr(self, "check_deadline", lambda: None),
                    **({"environment_observation_sha256":self.ra_binding["initial_environment_observation_sha256"],"backend_reader":self._ra_backend_digest} if getattr(self,"ra_enabled",False) else {})
                ),
            )
        return value

    def _profile_plan(self, spec):
        return (
            operations.parse_selected(self.records.raw(spec["profile_sha256"])),
            operations.parse_selected(self.records.raw(spec["plan_sha256"])),
        )

    def verify_sampling_assurance(self, *, verify_inventory=True):
        """Fail before protected readers/provider access, with fresh domain facts."""
        if self.ra_enabled and self.local_only:
            from . import s12_b2_ra_g1_resources as ra
            return ra.verify_local_assurance(self,verify_inventory=verify_inventory)
        spec = self.settings.get("campaign")
        if spec is None:
            spec = (
                self.config.get("bootstrap")
                if self.phase == "prepare-bootstrap"
                else None
            )
        if type(spec) is not dict or not {
            "profile_sha256",
            "plan_sha256",
            "start_sha256",
        } <= set(spec):
            return
        profile, plan = self._profile_plan(spec)
        contract = operations.for_profile(profile)
        if not getattr(contract, "AP_ENABLED", False):
            return
        from . import s12_wf_ap2_assurance as assurance
        if self.ra_enabled:
            from . import s12_ra_g1_assurance as assurance

        start = contract.parse(self.records.raw(spec["start_sha256"]), contract.START)
        self.authority.configuration_scope_sha256 = assurance.configuration_scope(
            self.config, plan=plan
        )
        self.authority.test_only = self.test_only
        record = self.authority.sampling_bound(profile, start)
        contract.validate_bound(
            record,
            profile,
            start,
            configuration_scope_sha256=self.authority.configuration_scope_sha256,
        )
        if verify_inventory:
            contract.verify_descriptors()
            self._source_check()
            actual_hash = b.digest(self._actual_runtime_inventory(successor=True))
            b.require(
                actual_hash == start["runtime_inventory_sha256"], "B2_RUNTIME_INVENTORY"
            )
            b.require(
                self._sampling_runtime_inventory_sha256 in (None, actual_hash),
                "B2_RUNTIME_INVENTORY",
            )
            self._sampling_runtime_inventory_sha256 = actual_hash
        else:
            b.require(
                self._sampling_runtime_inventory_sha256
                == start["runtime_inventory_sha256"],
                "B2_RUNTIME_INVENTORY",
            )
        assurance.verify_runtime(
            record, self.authority, {"profile": profile, "plan": plan, "start": start}
        )

    def _bind_resource_command(self):
        """Reserve the reviewed command before any derived namespace exists."""
        if self.resource_binding is None:
            return
        b.require(self.resource_ledger is None, "B2_RS1_COMMAND_BINDING")
        if self.ra_enabled:
            from . import s12_b2_ra_g1_graph as ra_graph
            return ra_graph.bind_runtime(self)
        from . import s12_b2_resources as resources

        raw = self.records.raw(self.resource_binding["model_sha256"])
        from . import s12_b2_acceptance_graph as graph

        value = io.metadata(raw)
        if graph.is_model(value):
            graph.bind_runtime(self)
            return
        model = resources.parse(raw, resources.MODEL)
        b.require(
            b.sha(raw).hex() == self.resource_binding["model_sha256"],
            "B2_RS1_MODEL_CHANGED",
        )
        runtime_inventory = self._actual_runtime_inventory()
        resources.authority_check(
            model,
            self.records,
            self.authority,
            now=self.clock.utc(),
            source_hash=b.digest(self.settings["source_files"]),
            runtime_hash=b.digest(runtime_inventory),
            workload_hash=model["workload_sha256"],
        )
        filesystem = os.statvfs(self.output.parent)
        b.require(
            model["capacity_bytes"] <= self.settings["phase_disk_capacity_bytes"]
            and model["capacity_bytes"] <= filesystem.f_bavail * filesystem.f_frsize
            and model["capacity_inodes"] <= filesystem.f_favail,
            "B2_RS1_CAPACITY_UNAVAILABLE",
        )
        plan_binding = None
        if self.settings["campaign"] is not None:
            profile, plan = RuntimePort._profile_plan(self, self.settings["campaign"])
            operations.validate_plan(plan, profile)
            b.require(
                profile.get("schema_version")
                == "stage12_development_operations_b2_rs1_v1"
                and profile["resource_retention_model"] == model,
                "B2_RS1_PLAN_BINDING",
            )
            resources.validate_plan_model(model, plan)
            plan_binding = resources.workload_binding(plan)
        command_id = self.resource_binding["command_id"]
        b.require(command_id <= len(model["commands"]), "B2_RS1_COMMAND_EXHAUSTED")
        command = model["commands"][command_id - 1]
        b.require(
            command["phase"] == self.phase
            and command["scope_sha256"]
            == resources.command_scope(self.config, plan_binding=plan_binding),
            "B2_RS1_COMMAND_BINDING",
        )
        b.require(
            command["max_duration_ms"] <= self.settings["phase_duration_ms"]
            and command["max_memory_bytes"] <= self.settings["phase_memory_bytes"]
            and command["max_generated_bytes"]
            <= self.settings["phase_generation_bound_bytes"]
            and command["max_generated_inodes"]
            <= self.settings["phase_generation_max_files"],
            "B2_RS1_COMMAND_BOUND",
        )
        self.resource_command = command
        self.resource_command_deadline = self.clock.now_ns() + (
            command["max_duration_ms"] * 1_000_000
        )
        self.check_deadline()
        ledger_root = Path(self.settings["output_parent"]) / ("rs1_" + b.digest(model))
        b.require(
            ledger_root not in {self.output, self.scratch}
            and not self.output.is_relative_to(ledger_root)
            and not self.scratch.is_relative_to(ledger_root),
            "B2_RUNTIME_PATH",
        )
        self.resource_ledger = resources.CommandLedger(
            ledger_root,
            model,
            command_id=command_id,
            phase=self.phase,
            scope_hash=command["scope_sha256"],
            check=self.check_deadline,
        )
        self.resource_model = model
        selected = self.resource_binding.get("allocation_limits_sha256")
        if selected is not None:
            from . import s12_b2_allocation_limits as limits

            value = limits.parse(self.records.raw(selected))
            limits.validate_binding(value, model, command)
            self.records.raw(value["review_sha256"])
            self.records.raw(value["native_bound_evidence_sha256"])
            self.authority.require(
                "resource_retention_allocation_limits", selected, value
            )
            self.allocation_limits = limits.Controls(value, check=self.check_deadline)
            self._stack.enter_context(io.allocation_controls(self.allocation_limits))

    def _rules(self):
        if self.response_rules is not None:
            return
        x = io.metadata(self.records.raw(self.settings["response_rules_sha256"]))
        b.require(
            set(x)
            == {
                "version",
                "layers",
                "sources",
                "echo_by_mode",
                "country_echo",
                "interpretation_sha256",
            }
            and x["version"] == "stage12_runtime_response_rules_v1"
            and x["interpretation_sha256"]
            == self.settings["gate"]["interpretation_hash"],
            "B2_INTERPRETATION_INVALID",
        )
        b.require(
            all(
                type(x[k]) is list
                and x[k] == sorted(set(x[k]))
                and x[k]
                and all(type(v) is str and v for v in x[k])
                for k in ("layers", "sources")
            ),
            "B2_INTERPRETATION_INVALID",
        )
        b.require(
            set(x["echo_by_mode"]) == {"FULL_TEXT", "STRUCTURED"},
            "B2_INTERPRETATION_INVALID",
        )

        def expected(work):
            if self._catalog is None:
                self._catalog_for_verify()
            core = self._catalog.core(work["query_semantic_id"])
            result = {}
            rules = x["echo_by_mode"][core["search_mode"]]
            b.require(
                type(rules) is dict and 1 <= len(rules) <= 16,
                "B2_INTERPRETATION_INVALID",
            )
            for field, source in rules.items():
                if source == "RESULT_LIMIT":
                    result[field] = work["result_limit"]
                elif source == "COUNTRY_ECHO":
                    b.require(
                        core["boundary_country"] in x["country_echo"],
                        "B2_INTERPRETATION_INVALID",
                    )
                    result[field] = x["country_echo"][core["boundary_country"]]
                else:
                    b.require(
                        source in core and source not in ("search_mode", "endpoint"),
                        "B2_INTERPRETATION_INVALID",
                    )
                    if core[source] is not None:
                        result[field] = core[source]
            return result

        self.response_rules = pipeline.ResponseRules(
            frozenset(x["layers"]),
            frozenset(x["sources"]),
            expected,
            self.settings["response_rules_sha256"],
        )

    def dispatch(self, work, target, hooks):
        b.require(
            self.mode == "EXACT_AUTHORIZED_DISPATCH" and self.phase in DISPATCH,
            "B2_RUNTIME_DISPATCH_UNISSUED",
        )
        self.check_deadline()
        self.verify_sampling_assurance(verify_inventory=False)
        self.gate.before_dispatch()
        self.runtime_key()
        profile = self._transport_profile()
        owner = self

        class Hooks:
            def started(self, ns):
                hooks.started(ns)

            def signal(self, *args):
                hooks.signal(*args)

            def completed(self, value):
                hooks.completed(value)

            def attempt_deadline_ns(self, started, maximum):
                return min(owner.deadline, hooks.attempt_deadline_ns(started, maximum))

            def emit(self, write, deadline):
                def check():
                    owner.check_deadline()
                    deadline()

                hooks.emit(write, check)

        sender = self._test["send"] if self.test_only else transport.send
        return sender(
            target, profile, self._key, transport_operations.Operations(), hooks=Hooks()
        )

    def _transport_profile(self):
        """Read the exact reviewed transport bytes before provider access/emission."""
        p = self.settings["transport"]
        b.require(
            type(p) is dict
            and set(p)
            == {
                "origin",
                "approved_ip",
                "configuration_evidence_sha256",
                "target_limit",
                "header_limit",
            },
            "B2_RUNTIME_TRANSPORT",
        )
        b.require(self._campaign is not None, "B2_RUNTIME_CAMPAIGN")
        digest = self._campaign[0]["transport_profile_sha256"]
        b.require(
            self.records.raw(digest) == b.canonical(p), "B2_RUNTIME_TRANSPORT_BINDING"
        )
        self.records.raw(p["configuration_evidence_sha256"])
        self.authority.require("transport", digest, p)
        profile = transport.TransportProfile(
            p["origin"],
            p["approved_ip"],
            bytes.fromhex(p["configuration_evidence_sha256"]),
            p["target_limit"],
            p["header_limit"],
        )
        profile.validate()
        b.require(
            p["origin"] == "https://geocode.safe-frankfurt.de", "B2_RUNTIME_TRANSPORT"
        )
        return profile

    def postflight_records(self, close_info):
        self.check_deadline()
        x = object_at(self.settings["postflight_bundle_path"])
        b.require(
            set(x) == {"version", "close_info_sha256", "records", "authority_sha256"}
            and x["version"] == "stage12_runtime_postflight_bundle_v1"
            and x["close_info_sha256"] == b.digest(close_info),
            "CLOSURE_MISSING",
        )
        self.authority.require("postflight_bundle", x["authority_sha256"], x)
        bounds = pipeline.acquisition_bounds(
            self.records, self._campaign[0], "postflight"
        )
        b.require(
            type(x["records"]) is list
            and 0 < len(x["records"]) <= bounds["max_records"],
            "B2_ADMIN_BOUND",
        )
        loaders = []
        total = 0
        for item in x["records"]:
            b.require(set(item) == {"path", "sha256", "bytes"}, "B2_ADMIN_BOUND")
            b.uint(item["bytes"], True)
            total += item["bytes"]
            b.require(
                item["bytes"] <= bounds["max_record_bytes"]
                and total <= bounds["max_total_bytes"],
                "B2_ADMIN_BOUND",
            )

            def load(item=item):
                self.check_deadline()
                raw = io.read(absolute(item["path"]), limit=item["bytes"])
                b.require(
                    len(raw) == item["bytes"] and b.sha(raw).hex() == item["sha256"],
                    "B2_EVIDENCE_CHANGED",
                )
                self.secret_guard(raw)
                return raw

            loaders.append(load)
        return tuple(loaders)

    def prepare_bootstrap(self):
        """Finite local preflight acquisition; returns the real future admission input."""
        b.require(
            self.phase == "prepare-bootstrap" and self.mode == "OFFLINE_ONLY",
            "B2_RUNTIME_DISPATCH_UNISSUED",
        )
        self.gate.check()
        x = self.config["bootstrap"]
        b.require(
            type(x) is dict
            and set(x)
            == {
                "profile_sha256",
                "plan_sha256",
                "start_sha256",
                "segment_nonce",
                "epoch_id",
                "records",
                "authority_sha256",
                "writer_release_evidence_sha256",
                "previous_hash",
            },
            "B2_RUNTIME_BOOTSTRAP",
        )
        profile = operations.parse_selected(self.records.raw(x["profile_sha256"]))
        plan = operations.parse_selected(self.records.raw(x["plan_sha256"]))
        start = operations.parse_selected(self.records.raw(x["start_sha256"]))
        operations.verify_authorities(profile, plan, start, self.gate)
        b.require(
            plan["window_plan_sha256"] == self.gate.window_hash
            and plan["population_scope"] == self.population_scope,
            "B2_RUNTIME_BOOTSTRAP",
        )
        bounds = pipeline.acquisition_bounds(self.records, profile, "preflight")
        b.require(
            type(x["records"]) is list
            and 0 < len(x["records"]) <= bounds["max_records"],
            "B2_ADMIN_BOUND",
        )
        total, loaders = 0, []
        for item in x["records"]:
            b.require(set(item) == {"path", "sha256", "bytes"}, "B2_ADMIN_BOUND")
            b.uint(item["bytes"], True)
            total += item["bytes"]
            b.require(
                item["bytes"] <= bounds["max_record_bytes"]
                and total <= bounds["max_total_bytes"],
                "B2_ADMIN_BOUND",
            )

            def load(item=item):
                self.check_deadline()
                raw = io.read(absolute(item["path"]), limit=item["bytes"])
                b.require(
                    len(raw) == item["bytes"] and b.sha(raw).hex() == item["sha256"],
                    "B2_EVIDENCE_CHANGED",
                )
                self.secret_guard(raw)
                return raw

            loaders.append(load)
        self.authority.require("bootstrap_inputs", x["authority_sha256"], x)
        value = pipeline.prepare_bootstrap(
            self.output,
            records=self.records,
            raw_factory=lambda: tuple(loaders),
            clock=self.clock,
            profile=profile,
            plan=plan,
            start=start,
            segment_nonce=x["segment_nonce"],
            epoch_id=x["epoch_id"],
            authority=self.gate,
            authority_hash=x["authority_sha256"],
            writer_release_evidence=x["writer_release_evidence_sha256"],
            secret_guard=self.secret_guard,
            previous_hash=x["previous_hash"],
        )
        self.check_deadline()
        return value

    def verify_campaign(self):
        self.campaign_inputs()
        if self._reader is None:
            self._reader = phase_io.CampaignReader(
                self.segment,
                catalog=self._catalog_for_verify(),
                rules=self.response_rules,
                gate=self.gate,
                closure_hash=self.config["campaign_closure_sha256"],
                scratch=self.scratch.parent / (self.scratch.name + "_runtime_reader"),
                control_adapters=self.control_adapters,
            )
            self._stack.callback(self._reader.close)
        return self._reader.validate()

    def _catalog_for_verify(self):
        self.gate.check()
        binding = self.records.get(
            self.config["input_binding_sha256"], "stage11_input_binding"
        )
        self.authority.require("protected_input", b.digest(binding), binding)
        if self._catalog is None:
            self._catalog = catalogs.Catalog(
                absolute(self.config["catalog_path"]),
                binding,
                expected_file_sha256=self.config["catalog_file_sha256"],
            )
            self._stack.callback(self._catalog.close)
        self._catalog.verify()
        return self._catalog

    def open_catalog(self):
        """Explicit synthetic constructor tests still use the real catalog reader."""
        b.require(self.test_only, "B2_ACCEPTED_POPULATION_REQUIRED")
        self.gate.check()
        binding = self.records.get(
            self.config["input_binding_sha256"], "stage11_input_binding"
        )
        self.authority.require("protected_input", b.digest(binding), binding)
        return self._catalog_for_verify()

    def pause_requested(self):
        self.check_deadline()
        return (
            self.phase in DISPATCH
            and self.clock.now_ns() - self.started_ns
            >= self.settings["campaign"]["pause_after_ms"] * 1000000
        )

    def notice(self):
        if isinstance(self.gate, PreparationGate):
            return None
        path = Path(self.settings["window_state_path"]).parent / (
            self.gate.window_hash + "_CLOSED.json"
        )
        if path.exists():
            return b.sha(io.read(path)).hex()
        state = self.window_state(self.gate.window_hash)
        return state["evidence_sha256"] if state["state"] != "OPEN" else None

    def close(self):
        if not self._closed:
            primary = None
            try:
                self.check_deadline()
                if self.work is not None:
                    self.work.verify()
                self._source_check()
                if self._sampling_runtime_inventory_sha256 is not None:
                    spec = self.settings.get("campaign") or self.config.get("bootstrap")
                    operations.for_profile(
                        self._profile_plan(spec)[0]
                    ).verify_descriptors()
                    b.require(
                        b.digest(self._actual_runtime_inventory(successor=True))
                        == self._sampling_runtime_inventory_sha256,
                        "B2_RUNTIME_INVENTORY",
                    )
                if self.local_only:
                    if self.ra_enabled:
                        self.verify_sampling_assurance()
                    self.gate.check()
                self.reconcile_generation()
            except BaseException as error:
                primary = error
            try:
                if self.resource_ledger is not None and callable(
                    getattr(self.resource_ledger, "prepare_finish", None)
                ):
                    self.resource_ledger.prepare_finish()
                if self.allocation_limits is not None:
                    self.allocation_limits.persist_usage(
                        Path(self.settings["temporary_root"]) / "allocation_usage.json"
                    )
            except BaseException as error:
                if primary is None:
                    primary = error
            try:
                self._stack.close()
            except BaseException as error:
                if primary is None:
                    primary = error
            try:
                if primary is None:
                    # Closing an SQLite connection can flush a journal. Account
                    # once more after all writers/readers and temp users close.
                    self.reconcile_generation()
            except BaseException as error:
                if primary is None:
                    primary = error
            try:
                if primary is None and self.resource_ledger is not None:
                    self.resource_ledger.finish(
                        roots=list(self._generation_roots),
                        max_entries=self.settings["phase_generation_max_files"],
                    )
            except BaseException as error:
                if primary is None:
                    primary = error
            finally:
                if self.local_only and self.offline_guard is not None:
                    self.offline_guard.close()
                self._key = None
                self._closed = True
            if primary is not None:
                raise primary


def create_port(config,*,resource_role_entry_ns=None):
    return RuntimePort(config,resource_role_entry_ns=resource_role_entry_ns)

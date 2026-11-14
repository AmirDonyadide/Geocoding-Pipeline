"""Real RA-G1 public/representative evidence resolution.

Resource observations are not permissions or complete enforcement proofs. Old
M2 records never pass this resolver. Synthetic transport authority is explicitly
separate from an ordinary public service grant.
"""

from __future__ import annotations

import threading
import json
import hashlib
import os
import stat
from pathlib import Path

from . import s12_public_operations as o
from . import s12_retrieval_contract as c
from . import s12_storage as io
from . import s12_ra_g1_assurance as a

REVIEW = "stage12_public_review_binding_ra_g1_v1"
DIAGNOSTIC_REVIEW = "stage12_representative_review_binding_ra_g1_v1"
BOUND_REVIEW = "stage12_resource_bound_review_ra_g1_v1"
ROLES = (
    "runtime_bounds",
    "technical_reviews",
    "selections",
    "observations",
    "capacities",
    "adoptions",
    "policies",
    "graphs",
    "risks",
    "owner_reports",
    "logical",
)

PUBLIC_ROLES = ROLES + ("representative_outcomes",)


SHARED_ALLOCATION_DESCRIPTOR = "stage12_ra_g1_shared_lease_public_allocation_selection_v1"


def shared_allocation_descriptor():
    """Pure PUBLIC wire delta; no authority, bootstrap exception or source I/O."""
    from . import s12_ra_g1_accounting as accounting
    from .s12_wf_ap2_scratch import RA_G1_CAPS

    model = accounting.descriptor(shared_lease_successor=True)
    return dict(
        descriptor_version=SHARED_ALLOCATION_DESCRIPTOR,
        scope="PUBLIC_SYNTHETIC_ONLY",
        closed=True,
        outer_shape_and_budgets="EXISTING_PUBLIC_WORKFLOW_FIELDS_AND_LIMITS_UNCHANGED",
        source_parser="scripts/stage12_ra_g1_public_workflow.py::validate_selection",
        accounting_inventory=accounting.SHARED_LEASE_VERSION,
        bootstrap_proof_record_count=0,
        logical_scratch_bytes=sum(RA_G1_CAPS.values()),
        monitor_writer_readback_bytes=model["monitor_writer_readback_bytes"],
        monitor_writer_max_read_calls=model["monitor_writer_original_readback_calls"]
        + model["monitor_writer_codec_readback_calls"],
        monitor_writer_original_readback_eof=model["monitor_writer_original_readback_eof"],
        maximum_first_observation_gap_ms=1000,
        bootstrap_prefix_authority="DENIED",
        protected_input_authority="DENIED",
        execution_permission="NOT_ISSUED",
    )



def _base():
    from . import s12_public_runtime

    return s12_public_runtime.Authority


class Authority:
    """Scoped resolver; authority is exact original bytes and genuine lineage."""

    test_only = False
    service_authority = True
    diagnostic_scope = None

    def __init__(
        self,
        config,
        bundle,
        review,
        review_hash,
        repository,
        git_sha,
        clock,
        *,
        deadline_check=None,
        diagnostic=False,
        defer_source_fence=False,
        source_counter_ledger=None,
        allocation_controls=None,
    ):
        self.config, self.bundle, self.review, self.review_hash = (
            config,
            Path(bundle),
            review,
            review_hash,
        )
        self.repository, self.git_sha, self.clock = Path(repository), git_sha, clock
        self._source_root_identity = a.private_root_identity(self.repository)
        self._deadline_check = deadline_check or (lambda: None)
        self.active = self.start = None
        self._lock = threading.RLock()
        self._enforcement_lock = self._lock
        self._source_counter_ledger = source_counter_ledger
        if source_counter_ledger is not None:
            from .s12_ra_g1_source_counters import SourceCounterLedger

            o.require(
                not diagnostic
                and isinstance(source_counter_ledger, SourceCounterLedger)
                and source_counter_ledger.process_pid == os.getpid(),
                "RA_G1_HANDOFF",
            )
        self._local_enforcement_checks = self._runtime_inventory_checks = 0
        self._local_read_calls = self._local_read_bytes = 0
        self._identity_limit = self._read_call_limit = self._read_byte_limit = None
        self._runtime_inventory_limit = None
        self.resource_monitor = None
        self._coordinator = None
        self._root_charge_before_phase = 0
        self._segment_charge_at_entry = 0
        self.allocation_controls = allocation_controls
        self.diagnostic_scope = "REPRESENTATIVE_NO_SERVICE" if diagnostic else None
        self.service_authority = not diagnostic
        self.configuration_scope_sha256 = a.configuration_scope(config)
        o.require(
            set(review)
            == {
                "version",
                "scope",
                "disposition",
                "configuration_sha256",
                "report_sha256",
                "source_files",
                "resource_evidence",
            },
            "RA_G1_REVIEW_FIELDS",
        )
        o.require(
            review["version"] == (DIAGNOSTIC_REVIEW if diagnostic else REVIEW)
            and review["scope"]
            == ("REPRESENTATIVE_NO_SERVICE" if diagnostic else o.SCOPE)
            and review["disposition"] == "PASS",
            "RA_G1_REVIEW_SCOPE",
        )
        o.require(
            review["configuration_sha256"] == o.digest(config),
            "RA_G1_CONFIGURATION_BINDING",
        )
        o.require(
            c.sha(io.read(self.bundle / "integration_review.md")).hex()
            == review["report_sha256"],
            "RA_G1_REVIEW_CHANGED",
        )
        expected_roles = ROLES if diagnostic else PUBLIC_ROLES
        a.shape(review["resource_evidence"], {key: ["D"] for key in expected_roles})
        for values in review["resource_evidence"].values():
            o.require(
                1 <= len(values) <= 64 and values == sorted(set(values)),
                "RA_G1_EVIDENCE_INVENTORY",
            )
        o.require(
            type(review["source_files"]) is list
            and 1 <= len(review["source_files"]) <= 2048,
            "RA_G1_SOURCE_INVENTORY",
        )
        self._source_verified = False
        if not defer_source_fence:
            self.source_fence()
        self.recheck()
        if not diagnostic:
            self.verify_representative_release()

    @property
    def _original_read_calls(self):
        return (
            self._source_counter_ledger.source_read_calls
            if self._source_counter_ledger is not None
            else self._local_read_calls
        )

    @property
    def _original_read_bytes(self):
        return (
            self._source_counter_ledger.source_read_bytes
            if self._source_counter_ledger is not None
            else self._local_read_bytes
        )

    @property
    def _enforcement_checks(self):
        return (
            self._source_counter_ledger.identity_checks
            if self._source_counter_ledger is not None
            else self._local_enforcement_checks
        )

    def source_counter_snapshot(self):
        if self._source_counter_ledger is not None:
            return self._source_counter_ledger.snapshot_source()
        with self._lock:
            return {
                "source_read_calls": self._local_read_calls,
                "source_read_bytes": self._local_read_bytes,
                "identity_checks": self._local_enforcement_checks,
            }

    def source_fence(self):
        self._source_verified = False
        o.require(
            a.private_root_identity(self.repository) == self._source_root_identity,
            "RA_G1_SOURCE_CHANGED",
        )
        names = []
        for entry in self.review["source_files"]:
            self._deadline_check()
            o.require(
                set(entry) == {"path", "bytes", "sha256"}
                and type(entry["bytes"]) is int
                and 0 <= entry["bytes"] <= 64 * 2**20,
                "RA_G1_SOURCE_INVENTORY",
            )
            relative = Path(entry["path"])
            o.require(
                not relative.is_absolute()
                and ".." not in relative.parts
                and len(entry["path"].encode("utf8")) <= 512,
                "RA_G1_SOURCE_INVENTORY",
            )
            names.append(entry["path"])
            path = self.repository / relative
            parents = self._source_parent_identities(relative)
            info = path.lstat()
            o.require(
                path.is_file()
                and not path.is_symlink()
                and info.st_size == entry["bytes"],
                "RA_G1_SOURCE_CHANGED",
            )
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                opened = os.fstat(fd)
                h = hashlib.sha256()
                remaining = entry["bytes"]
                while remaining:
                    self._deadline_check()
                    self.charge_original(1, 0)
                    raw = os.read(fd, min(4096, remaining))
                    self.charge_original(0, len(raw))
                    o.require(bool(raw), "RA_G1_SOURCE_CHANGED")
                    h.update(raw)
                    remaining -= len(raw)
                self._deadline_check()
                self.charge_original(1, 0)
                extra = os.read(fd, 1)
                self.charge_original(0, len(extra))
                o.require(
                    not extra
                    and self._stat_identity(info)
                    == self._stat_identity(opened)
                    == self._stat_identity(os.fstat(fd))
                    == self._stat_identity(path.lstat())
                    and h.hexdigest() == entry["sha256"],
                    "RA_G1_SOURCE_CHANGED",
                )
                o.require(
                    parents == self._source_parent_identities(relative),
                    "RA_G1_SOURCE_CHANGED",
                )
            finally:
                os.close(fd)
        o.require(names == sorted(set(names)), "RA_G1_SOURCE_INVENTORY")
        o.require(
            a.private_root_identity(self.repository) == self._source_root_identity,
            "RA_G1_SOURCE_CHANGED",
        )
        self._source_verified = True

    def verify_diagnostic_source(self, path, entry):
        """Fresh selected-member pin; same guards/charges as the full fence.

        This grants no access. The caller's finite diagnostic map can name only
        already-authorized source originals; the ordinary full fence still runs.
        """
        o.require(type(entry) is dict and set(entry) == {"path", "bytes", "sha256"}
                  and type(entry["path"]) is str and type(entry["bytes"]) is int
                  and 0 <= entry["bytes"] <= 2**20
                  and entry in self.review["source_files"], "RA_G1_SOURCE_INVENTORY")
        o.require(Path(path) == self.repository / entry["path"], "RA_G1_SOURCE_INVENTORY")
        self._deadline_check()
        o.require(a.private_root_identity(self.repository) == self._source_root_identity, "RA_G1_SOURCE_CHANGED")
        relative = Path(entry["path"])
        o.require(
            not relative.is_absolute()
            and ".." not in relative.parts
            and len(entry["path"].encode("utf8")) <= 512,
            "RA_G1_SOURCE_INVENTORY",
        )
        path = self.repository / relative
        parents = self._source_parent_identities(relative)
        info = path.lstat()
        o.require(
            path.is_file()
            and not path.is_symlink()
            and info.st_size == entry["bytes"],
            "RA_G1_SOURCE_CHANGED",
        )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            h = hashlib.sha256()
            remaining = entry["bytes"]
            while remaining:
                self._deadline_check()
                self.charge_original(1, 0)
                raw = os.read(fd, min(4096, remaining))
                self.charge_original(0, len(raw))
                o.require(bool(raw), "RA_G1_SOURCE_CHANGED")
                h.update(raw)
                remaining -= len(raw)
            self._deadline_check()
            self.charge_original(1, 0)
            extra = os.read(fd, 1)
            self.charge_original(0, len(extra))
            o.require(
                not extra
                and self._stat_identity(info)
                == self._stat_identity(opened)
                == self._stat_identity(os.fstat(fd))
                == self._stat_identity(path.lstat())
                and h.hexdigest() == entry["sha256"],
                "RA_G1_SOURCE_CHANGED",
            )
            o.require(
                parents == self._source_parent_identities(relative),
                "RA_G1_SOURCE_CHANGED",
            )
        finally:
            os.close(fd)
        o.require(a.private_root_identity(self.repository) == self._source_root_identity, "RA_G1_SOURCE_CHANGED")
        return True

    def _source_parent_identities(self, relative):
        """Finite pinned-source parents, before and after each original read."""
        result = []
        parent = self.repository
        for component in relative.parts[:-1]:
            self._deadline_check()
            parent = parent / component
            info = parent.lstat()
            o.require(
                stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o022,
                "RA_G1_SOURCE_CHANGED",
            )
            result.append(self._stat_identity(info))
        return result

    @staticmethod
    def _stat_identity(info):
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

    @classmethod
    def _source_identity(cls, path):
        return cls._stat_identity(path.lstat())

    def _charge_original(self, size):
        return self.charge_original(1, size)

    def charge_original(self, calls, size):
        o.uint(calls)
        o.uint(size)
        with self._lock:
            if self._source_counter_ledger is not None:
                self._source_counter_ledger.read_charge(calls, size)
            else:
                self._local_read_calls += calls
                self._local_read_bytes += size
            if self._read_call_limit is not None:
                o.require(
                    self._original_read_calls <= self._read_call_limit
                    and self._original_read_bytes <= self._read_byte_limit,
                    "RA_G1_ORIGINAL_READ_BUDGET",
                )

    def _resource_evidence(self, identity, role):
        self._deadline_check()
        o.validate_type(identity, "D")
        o.require(
            role in (ROLES if self.diagnostic_scope else PUBLIC_ROLES)
            and identity in self.review["resource_evidence"][role],
            "RA_G1_EVIDENCE_SCOPE",
        )
        raw = io.read(
            self.bundle / "resource_evidence" / (identity + ".record"), limit=65536
        )
        value = json.loads(raw, object_pairs_hook=io.pairs)
        o.require(role == "capacities" or type(value) is dict, "RA_G1_EVIDENCE_SCOPE")
        o.require(
            c.canonical(value) == raw and c.sha(raw).hex() == identity,
            "RA_G1_EVIDENCE_CHANGED",
        )
        self.charge_original(1, len(raw))
        return value

    def verify_representative_release(self):
        identity = self.config.get("representative_validation_sha256")
        record = self._resource_evidence(identity, "representative_outcomes")
        if record.get("schema_version") == a.REP_COVERAGE_OUTCOME:
            a.validate_rep_coverage_outcome(record)
        else:
            a.shape(
                record,
                {
                    "schema_version": "=stage12_ra_g1_representative_independent_outcome_v1",
                    "scope": "=REPRESENTATIVE_NO_SERVICE",
                    "source_git_sha": "G",
                    "selection_sha256": "D",
                    "input_sha256": "D",
                    "artifact_manifest_sha256": "D",
                    "independent_report_sha256": "D",
                    "disposition": "=PASS_COMPLETE_REPRESENTATIVE",
                    "expected_attempts": "=106",
                    "maximum_attempts": "=107",
                    "scenarios_completed": "=4",
                    "actual_reopening": "B",
                    "sampling_and_monitor_coverage": "=COMPLETE_SELECTED_SCOPE",
                    "authority_attribution": "=INDEPENDENT_AGENT_OUTCOME_NOT_HUMAN_OR_OPERATOR",
                },
            )
        o.require(
            record["source_git_sha"] == self.git_sha
            and record["actual_reopening"] is True,
            "RA_G1_REPRESENTATIVE_SOURCE_MISMATCH",
        )
        # The original report and complete immutable artifact manifest are
        # separately retained and freshly rehashed; a D-shaped string is not evidence.
        for field, suffix in (
            ("independent_report_sha256", ".md"),
            ("artifact_manifest_sha256", ".manifest"),
        ):
            raw = io.read(
                self.bundle / "resource_evidence" / (record[field] + suffix),
                limit=4 * 2**20,
            )
            self.charge_original(1, len(raw))
            o.require(
                c.sha(raw).hex() == record[field],
                "RA_G1_REPRESENTATIVE_EVIDENCE_CHANGED",
            )
        return record

    def sampling_bound(self, profile, start):
        if profile.get("schema_version")=="stage12_transport_operations_rep_coverage_ra_g1_v1":
            from . import s12_ra_g1_rep_coverage_contract as contract
        elif profile.get("schema_version")=="stage12_transport_operations_rep_fair_service_ra_g1_v1":
            from . import s12_ra_g1_rep_fair_contract as contract
        elif profile.get("schema_version")=="stage12_transport_operations_rep_ack_queue_ra_g1_v1":
            from . import s12_ra_g1_rep_ack_contract as contract
        else:
            from . import s12_ra_g1_contract as contract

        record = self._resource_evidence(
            profile["sampling_runtime_bound_sha256"], "runtime_bounds"
        )
        a.validate_record(
            record, profile, start, contract, self.configuration_scope_sha256
        )
        o.require(
            record["source_inventory_sha256"] == o.digest(self.review["source_files"]),
            "RA_G1_SOURCE_INVENTORY",
        )
        expected_scope = (
            "REPRESENTATIVE_NO_SERVICE" if self.diagnostic_scope else o.SCOPE
        )
        o.require(record["scope"] == expected_scope, "RA_G1_AUTHORITY_SCOPE")
        with self._lock:
            for name, value in (
                ("_identity_limit", record["maximum_identity_checks"]),
                ("_read_call_limit", record["maximum_original_read_calls"]),
                ("_read_byte_limit", record["maximum_original_read_bytes"]),
            ):
                current = getattr(self, name)
                setattr(self, name, value if current is None else min(current, value))
            o.require(
                self._original_read_calls <= self._read_call_limit
                and self._original_read_bytes <= self._read_byte_limit,
                "RA_G1_ORIGINAL_READ_BUDGET",
            )
        if self._source_counter_ledger is not None:
            self._source_counter_ledger.constrain(record)
        technical = self._resource_evidence(
            record["technical_review_sha256"], "technical_reviews"
        )
        subject = dict(record)
        subject.pop("technical_review_sha256")
        o.require(
            set(technical)
            == {
                "schema_version",
                "scope",
                "disposition",
                "bound_scope_sha256",
                "implementation_review_sha256",
            }
            and technical["schema_version"] == BOUND_REVIEW
            and technical["scope"] == record["scope"]
            and technical["disposition"] == "PASS"
            and technical["bound_scope_sha256"] == o.digest(subject)
            and technical["implementation_review_sha256"]
            == self.review["report_sha256"],
            "RA_G1_BOUND_REVIEW",
        )
        return record

    def initial_resource_facts(self, record):
        facts = self._resource_evidence(
            record["initial_environment_observation_sha256"], "observations"
        )
        originals = self._resource_evidence(
            facts["observation_inventory_sha256"], "observations"
        )
        a.validate_environment_originals(facts, originals)
        return facts

    def resource_facts(self, record):
        initial = self.initial_resource_facts(record)
        return a.observe_current_facts(
            initial, check=self._deadline_check, read_charge=self.charge_original
        )[0]

    def charge_identity_check(self, record):
        self._deadline_check()
        with self._lock:
            if self._source_counter_ledger is not None:
                self._source_counter_ledger.checkpoint()
            else:
                self._local_enforcement_checks += 1
            o.require(
                self._enforcement_checks <= record["maximum_identity_checks"],
                "RA_G1_IDENTITY_BUDGET",
            )

    def charge_runtime_inventory_check(self, record):
        self._deadline_check()
        with self._lock:
            self._runtime_inventory_checks += 1
            limit = record.get(
                "maximum_runtime_inventory_checks",
                record.get("maximum_identity_checks"),
            )
            o.require(
                type(limit) is int and self._runtime_inventory_checks <= limit,
                "RA_G1_RUNTIME_INVENTORY_BUDGET",
            )

    def runtime_inventory_budget(self):
        limits = [
            self._resource_evidence(
                item["profile"]["sampling_runtime_bound_sha256"], "runtime_bounds"
            )["maximum_identity_checks"]
            for item in self.config["campaigns"]
        ]
        return {"maximum_runtime_inventory_checks": min(limits)}

    def resource_selection(self, record):
        return self._resource_evidence(record["selection_sha256"], "selections")

    def capacity_observation(self, record):
        o.require(self.active is not None, "RA_G1_AUTHORITY_UNBOUND")
        identity = self.active[0]["profile"]["resources"][
            "initial_capacity_observation_sha256"
        ]
        record = self._resource_evidence(identity, "capacities")
        root_original = self._resource_evidence(
            record["root_identity_inventory_sha256"], "capacities"
        )
        a.validate_capacity_originals(
            record,
            root_original,
            self._resource_evidence(
                record["filesystem_originals_sha256"], "capacities"
            ),
            self._resource_evidence(record["accounting_method_sha256"], "capacities"),
            self._resource_evidence(
                record["restrictions_inventory_sha256"], "capacities"
            ),
            root_path=root_original[0][0],
        )
        return record

    def add_source_counter_prefix(self, prefix):
        o.require(
            set(prefix)
            == {"source_read_calls", "source_read_bytes", "identity_checks"},
            "RA_G1_HANDOFF",
        )
        for value in prefix.values():
            o.uint(value)
        with self._lock:
            # Existing bootstrap reads remain charged; never overwrite deltas.
            if self._source_counter_ledger is not None:
                self._source_counter_ledger.add_verified_prefix(prefix)
            else:
                self._local_read_calls += prefix["source_read_calls"]
                self._local_read_bytes += prefix["source_read_bytes"]
                self._local_enforcement_checks += prefix["identity_checks"]
            if self._read_call_limit is not None:
                o.require(
                    self._original_read_calls <= self._read_call_limit
                    and self._original_read_bytes <= self._read_byte_limit
                    and self._enforcement_checks <= self._identity_limit,
                    "RA_G1_HANDOFF",
                )

    def register_coordinator(self, coordinator):
        o.require(self._coordinator is None, "RA_G1_COORDINATOR_ALREADY_REGISTERED")
        self._coordinator = coordinator
        self._segment_charge_at_entry = sum(coordinator.ra_charged_snapshot)
        o.require(
            self.allocation_controls is not None, "RA_G1_ALLOCATION_CONTROLS_REQUIRED"
        )
        coordinator.writer.allocation_controls = self.allocation_controls

    def release_coordinator(self):
        o.require(self._coordinator is not None, "RA_G1_COUNTER_SOURCE_REQUIRED")
        self._root_charge_before_phase += sum(self._coordinator.ra_charged_snapshot)
        self._coordinator = None

    def counters(self):
        from . import s12_ra_g1_monitor as monitor

        o.require(
            self.allocation_controls is not None, "RA_G1_ALLOCATION_CONTROLS_REQUIRED"
        )
        usage = self.allocation_controls.snapshot()
        values = {key: usage["invocations"][key] for key in monitor.ROLES}
        current = (
            sum(self._coordinator.ra_charged_snapshot)
            if self._coordinator is not None
            else 0
        )
        source = self.source_counter_snapshot()
        values.update(
            application_write_reserved_bytes=usage["bytes"],
            application_creations_charged=usage["creations"],
            monitor_observations_charged=usage["monitor_rows"],
            monitor_write_bytes_charged=usage["monitor_bytes"],
            source_read_calls=source["source_read_calls"],
            source_read_bytes=source["source_read_bytes"],
            identity_checks=source["identity_checks"],
            segment_attempts=current - self._segment_charge_at_entry
            if self._coordinator is not None
            else 0,
            root_attempts=self._root_charge_before_phase + current,
        )
        return values

    def resource_prewrite(self, *, next_write_bytes, next_creations):
        self._deadline_check()
        o.require(self._source_verified, "RA_G1_SOURCE_NOT_VERIFIED")
        o.require(self.resource_monitor is not None, "RA_G1_MONITOR_REQUIRED")
        coverage_profile = (
            self.active is not None
            and self.active[0]["profile"].get("schema_version")
            == "stage12_transport_operations_rep_coverage_ra_g1_v1"
        )
        if not coverage_profile:
            self.resource_monitor.barrier(
                next_write_bytes=next_write_bytes, next_creations=next_creations
            )
        o.require(
            self.allocation_controls is not None, "RA_G1_ALLOCATION_CONTROLS_REQUIRED"
        )
        usage, limits = (
            self.allocation_controls.snapshot(),
            self.allocation_controls.selected["limits"],
        )
        o.require(
            usage["bytes"] + next_write_bytes
            <= limits["logical_write_bytes"] - limits["closure_reserve_bytes"]
            and usage["creations"] + next_creations
            <= limits["creations"] - limits["closure_reserve_creations"],
            "RA_G1_CLOSURE_RESERVE",
        )
        o.require(
            self.active is not None and self.start is not None,
            "RA_G1_AUTHORITY_UNBOUND",
        )
        profile = self.active[0]["profile"]
        record = self.sampling_bound(profile, self.start)
        original = self.capacity_observation(record)
        current, _ = a.observe_capacity(
            self.config.get(
                "output_directory", self.config.get("command_paths", {}).get("output")
            ),
            scope=record["scope"],
            selection_sha256=record["selection_sha256"],
            owner_reported_approval_sha256=record[
                "owner_reported_project_approval_sha256"
            ],
            accounting_method_sha256=original["accounting_method_sha256"],
            restrictions_inventory_sha256=original["restrictions_inventory_sha256"],
            observed_utc=self.clock.utc(),
            clock_ns=self.clock.now_ns,
        )
        a.check_capacity(
            current, next_write_bytes=next_write_bytes, next_creations=next_creations
        )
        if coverage_profile:
            # The sole strict barrier follows every potentially blocking
            # original/capacity read. No stale AP snapshot supplies safety.
            self.resource_monitor.barrier(
                next_write_bytes=next_write_bytes, next_creations=next_creations
            )

    def resource_current(self, *, next_write_bytes, next_creations):
        """Pure final-use guard after all potentially blocking callbacks."""
        o.require(
            self._source_verified and self.resource_monitor is not None
            and self.active is not None
            and self.active[0]["profile"].get("schema_version")
            == "stage12_transport_operations_rep_coverage_ra_g1_v1",
            "RA_G1_AUTHORITY_SCOPE",
        )
        o.require(self.allocation_controls is not None, "RA_G1_ALLOCATION_CONTROLS_REQUIRED")
        usage = self.allocation_controls.snapshot()
        limits = self.allocation_controls.selected["limits"]
        o.require(
            usage["bytes"] + next_write_bytes
            <= limits["logical_write_bytes"] - limits["closure_reserve_bytes"]
            and usage["creations"] + next_creations
            <= limits["creations"] - limits["closure_reserve_creations"],
            "RA_G1_CLOSURE_RESERVE",
        )
        return self.resource_monitor.require_current(
            next_write_bytes=next_write_bytes, next_creations=next_creations
        )

    def bind(self, item, plan, start):
        self.active, self.start = (item, plan), start

    def recheck(self, *, enforcement=False):
        self._deadline_check()
        o.require(
            self.config["window_start"] <= self.clock.utc() < self.config["window_end"],
            "RA_G1_EXPIRED",
        )
        for role, identity in self.config["sources"].items():
            o.require(
                c.sha(io.read(self.bundle / (role + ".record"))).hex() == identity,
                "RA_G1_AUTHORITY_CHANGED",
            )
        if enforcement and self.active is not None:
            a.verify_current_facts(
                self.sampling_bound(self.active[0]["profile"], self.start), self
            )

    def require(self, purpose, identity, context):
        resource_roles = {
            "resource_policy": ("policy_sha256", "policies"),
            "resource_adoption": ("adoption_sha256", "adoptions"),
            "resource_selection": ("selection_sha256", "selections"),
            "resource_technical_review": (
                "technical_review_sha256",
                "technical_reviews",
            ),
            "resource_invocation_graph": ("invocation_graph_sha256", "graphs"),
            "resource_risk_inventory": ("risk_inventory_sha256", "risks"),
            "owner_reported_project_approval": (
                "owner_reported_project_approval_sha256",
                "owner_reports",
            ),
        }
        if purpose in resource_roles or purpose in (
            "sampling_runtime_bound",
            "sampling_bound_review",
        ):
            self.recheck()
            o.require(
                self.active is not None and self.start is not None,
                "RA_G1_AUTHORITY_UNBOUND",
            )
            profile, plan = self.active[0]["profile"], self.active[1]
            record = self.sampling_bound(profile, self.start)
            expected_context = {"profile": profile, "plan": plan, "start": self.start}
            if purpose in resource_roles:
                field, role = resource_roles[purpose]
                o.require(
                    identity == record[field] and context == expected_context,
                    "RA_G1_AUTHORITY_SCOPE",
                )
                self._resource_evidence(identity, role)
            else:
                field, role = (
                    (None, "runtime_bounds")
                    if purpose == "sampling_runtime_bound"
                    else ("technical_review_sha256", "technical_reviews")
                )
                o.require(
                    identity
                    == (
                        profile["sampling_runtime_bound_sha256"]
                        if field is None
                        else record[field]
                    )
                    and context == (expected_context if field is None else record),
                    "RA_G1_AUTHORITY_SCOPE",
                )
            return
        if (
            purpose == "control_recipe"
            and self.diagnostic_scope == "REPRESENTATIVE_NO_SERVICE"
        ):
            from . import s12_public_matrix as matrix

            self.recheck()
            o.require(
                self.active is not None
                and identity == o.digest(matrix.check_descriptor())
                and context in self.active[1]["control_recipes"],
                "RA_G1_AUTHORITY_SCOPE",
            )
            return
        if purpose == "dispatch":
            o.require(self._source_verified, "RA_G1_SOURCE_NOT_VERIFIED")
        # The preserved generic dispatcher verifies exact public workload,
        # method, bytes, dates, source and control contexts. No M2 grant occurs.
        return _base().require(self, purpose, identity, context)


class ApplicationControls:
    """Checked public logical writes/invocations, never native physical maxima."""

    RA_ENABLED = True

    def __init__(self, selected, *, check, initial_usage=None):
        a.validate_selection(selected)
        self.selected, self.check = selected, check
        self.value = {"max_compressed_frame_bytes": 32 * 2**20}
        self._roles = dict.fromkeys(selected["limits"]["application_counters"], 0)
        self._bytes = self._creations = self._monitor_rows = self._monitor_bytes = 0
        self._lock = threading.Lock()
        if initial_usage is not None:
            o.require(
                set(initial_usage)
                == {
                    "invocations",
                    "bytes",
                    "creations",
                    "monitor_rows",
                    "monitor_bytes",
                },
                "RA_G1_HANDOFF",
            )
            o.require(
                set(initial_usage["invocations"]) == set(self._roles), "RA_G1_HANDOFF"
            )
            for key, value in initial_usage["invocations"].items():
                o.uint(value)
                o.require(
                    value <= self.selected["limits"]["application_counters"][key],
                    "RA_G1_HANDOFF",
                )
            for key in ("bytes", "creations", "monitor_rows", "monitor_bytes"):
                o.uint(initial_usage[key])
            limits = self.selected["limits"]
            o.require(
                initial_usage["bytes"] <= limits["logical_write_bytes"]
                and initial_usage["creations"] <= limits["creations"]
                and initial_usage["monitor_rows"] <= limits["monitor_rows"]
                and initial_usage["monitor_bytes"] <= limits["monitor_bytes"],
                "RA_G1_HANDOFF",
            )
            self._roles = dict(initial_usage["invocations"])
            self._bytes, self._creations = (
                initial_usage["bytes"],
                initial_usage["creations"],
            )
            self._monitor_rows, self._monitor_bytes = (
                initial_usage["monitor_rows"],
                initial_usage["monitor_bytes"],
            )

    def claim(self, role, size=0):
        self.check()
        o.uint(size)
        with self._lock:
            o.require(
                role in self._roles
                and self._roles[role]
                < self.selected["limits"]["application_counters"][role],
                "RA_G1_INVOCATION_BUDGET",
            )
            o.require(
                self._bytes + size <= self.selected["limits"]["logical_write_bytes"],
                "RA_G1_WRITE_BUDGET",
            )
            self._roles[role] += 1
            self._bytes += size
            if role in (
                "EXCLUSIVE_FILE",
                "EVENT_FILE",
                "ADMIN_FILE",
                "PARQUET_FILE",
                "RAW_PACK_FILE",
                "PREFIX_FILE",
                "COMPARISON_FILE",
            ):
                self._creations += 1
                o.require(
                    self._creations <= self.selected["limits"]["creations"],
                    "RA_G1_CREATION_BUDGET",
                )

    def bytes(self, amount):
        self.check()
        o.uint(amount)
        with self._lock:
            self._bytes += amount
            o.require(
                self._bytes <= self.selected["limits"]["logical_write_bytes"],
                "RA_G1_WRITE_BUDGET",
            )

    def reserve_components(self, amount, creations):
        """Permanent aggregate charge for independently bounded T3/helper owners."""
        self.check()
        o.uint(amount)
        o.uint(creations)
        with self._lock:
            self._bytes += amount
            self._creations += creations
            o.require(
                self._bytes <= self.selected["limits"]["logical_write_bytes"]
                and self._creations <= self.selected["limits"]["creations"],
                "RA_G1_COUNTER_LIMIT",
            )

    def monitor_charge(self, amount, creations):
        self.check()
        with self._lock:
            self._bytes += amount
            self._monitor_bytes += amount
            self._creations += creations
            if amount == 1024:
                self._monitor_rows += 1
            limits = self.selected["limits"]
            o.require(
                self._bytes <= limits["logical_write_bytes"]
                and self._monitor_bytes <= limits["monitor_bytes"]
                and self._monitor_rows <= limits["monitor_rows"]
                and self._creations <= limits["creations"],
                "RA_G1_MONITOR_BUDGET",
            )

    def snapshot(self):
        with self._lock:
            return {
                "invocations": dict(self._roles),
                "bytes": self._bytes,
                "creations": self._creations,
                "monitor_rows": self._monitor_rows,
                "monitor_bytes": self._monitor_bytes,
            }

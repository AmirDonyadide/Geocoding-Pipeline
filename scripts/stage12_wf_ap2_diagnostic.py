"""Opt-in future representative replay: real M2 proof, TEST_ONLY transport.

No selection/evidence is issued here. UNISSUED inputs are non-executable. The
shared Goethe guard, pinned original review bundle, LIVE_KERNEL_EVIDENCE and
actual fresh Linux observations are required before fixture/workload use.
The scheduler, capture, sampler, writer and openers are the production code.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import threading
import time

VERSION = "stage12_wf_ap2_representative_diagnostic_input_v1"
CONFIG_VERSION = "stage12_wf_ap2_representative_configuration_v1"
REVIEW_VERSION = "stage12_wf_ap2_representative_review_binding_v1"
SCOPE = "WF_AP2_REPRESENTATIVE_DIAGNOSTIC_TEST_ONLY_NO_SERVICE"
PHASES = (
    ("first64", 346000, 1817, 64),
    ("deep32_size40", 300000, 1572, 32),
    ("controls8", 180000, 200, 8),
    ("malformed", 180000, 0, 3),
)
_M2_PURPOSES = frozenset(
    (
        "sampling_runtime_bound",
        "sampling_bound_review",
        "sampling_enforcement_domain",
        "sampling_domain_coverage",
        "sampling_invocation_graph",
    )
)
_TOP = frozenset(
    (
        "version",
        "scope",
        "source_sha",
        "selection",
        "limits",
        "configuration",
        "phases",
        "runtime_inventory",
        "responses",
    )
)
_LIMITS = frozenset(
    (
        "seconds",
        "maximum_bytes",
        "maximum_creations",
        "rss_bytes",
        "maximum_input_bytes",
        "summary_reserve_bytes",
        "native_helper_bytes_reserve",
        "native_helper_creation_reserve",
    )
)


_CONFIG = frozenset(
    (
        "version",
        "window_start",
        "window_end",
        "sources",
        "transport",
        "campaigns",
        "resources",
        "public_validation_sha256",
        "command_paths",
    )
)


def require(condition, code="AP2_DIAGNOSTIC_INPUT_INVALID"):
    if not condition:
        raise RuntimeError(code)


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def hash_value(value, size=64):
    return (
        type(value) is str
        and len(value) == size
        and set(value) <= set("0123456789abcdef")
        and set(value) != {"0"}
    )


def input_scope(data):
    value = dict(data)
    value["selection"] = {
        key: cell
        for key, cell in data["selection"].items()
        if key != "authority_sha256"
    }
    return digest(value)


def validate_envelope(data, source_sha, *, for_execution):
    """Pure bounded metadata shape; this never creates a usable assurance record."""
    require(type(data) is dict and set(data) == _TOP)
    require(data["version"] == VERSION and data["scope"] == SCOPE)
    require(hash_value(source_sha, 40) and data["source_sha"] == source_sha)
    selected = data["selection"]
    require(
        type(selected) is dict
        and set(selected) == {"status", "authority_sha256", "resource_review_sha256"}
    )
    require(selected["status"] in ("UNISSUED", "ISSUED"))
    require(
        hash_value(selected["authority_sha256"])
        and hash_value(selected["resource_review_sha256"])
    )
    if for_execution:
        require(selected["status"] == "ISSUED", "AP2_DIAGNOSTIC_SELECTION_UNISSUED")
    limits = data["limits"]
    require(type(limits) is dict and set(limits) == _LIMITS)
    require(all(type(v) is int and 0 < v < 2**64 for v in limits.values()))
    require(limits["seconds"] == 7200 and limits["summary_reserve_bytes"] == 2**20)
    require(
        limits["maximum_input_bytes"] <= 64 * 2**20 and limits["maximum_bytes"] < 2**63
    )
    require(limits["rss_bytes"] <= 6 * 2**30)
    require(
        limits["maximum_bytes"]
        > limits["summary_reserve_bytes"] + limits["native_helper_bytes_reserve"]
    )
    config = data["configuration"]
    require(
        type(config) is dict
        and set(config) == _CONFIG
        and config.get("version") == CONFIG_VERSION
    )
    require(
        config.get("transport") == {"scope": SCOPE, "authority": "TEST_ONLY_NO_NETWORK"}
    )
    require(
        type(config.get("sources")) is dict
        and set(config["sources"])
        == {"owner", "operator", "policy_freeze", "selection", "transport"}
    )
    require(all(hash_value(value) for value in config["sources"].values()))
    require(type(config.get("campaigns")) is list and len(config["campaigns"]) == 4)
    require(
        type(config["command_paths"]) is dict
        and set(config["command_paths"])
        == {"source", "input", "output", "evidence_bundle"}
        and all(
            type(path) is str and Path(path).is_absolute()
            for path in config["command_paths"].values()
        )
    )
    require(type(data["phases"]) is list and len(data["phases"]) == 4)
    for item, phase, (label, duration, hold, count) in zip(
        config["campaigns"], data["phases"], PHASES, strict=True
    ):
        require(
            type(item) is dict and set(item) == {"label", "profile", "plan", "work"}
        )
        require(
            type(phase) is dict
            and set(phase) == {"label", "start", "epoch_id", "hold_regular_acks"}
        )
        require(
            item["label"] == phase["label"] == label
            and phase["hold_regular_acks"] == hold
        )
        require(hash_value(phase["epoch_id"]))
        profile, plan, start = item["profile"], item["plan"], phase["start"]
        require(profile.get("schema_version") == "stage12_transport_operations_v4")
        require(plan.get("schema_version") == "stage12_public_characterization_plan_v3")
        require(start.get("schema_version") == "stage12_public_operations_campaign_v3")
        require(
            start["client_git_sha"] == source_sha
            and start["profile_sha256"] == digest(profile)
            and start["plan_sha256"] == digest(plan)
        )
        require(start["runtime_inventory_sha256"] == digest(data["runtime_inventory"]))
        require(
            plan["budgets"]["active_duration_ms"]
            == plan["blocks"][0]["budget"]["active_duration_ms"]
            == duration
        )
        require(type(item["work"]) is list and len(item["work"]) == count)
        require(profile["transport_profile_sha256"] == digest(config["transport"]))
        require(profile["resources"] == config["resources"])
    require(config["resources"]["allocated_disk_bytes"] <= limits["maximum_bytes"])
    require(type(data["responses"]) is list and len(data["responses"]) == 48)
    keys = set()
    for row in data["responses"]:
        require(
            type(row) is dict
            and set(row)
            == {"fixture_id", "size", "raw_utf8", "payload_sha256", "origin"}
        )
        require(
            hash_value(row["fixture_id"])
            and type(row["size"]) is int
            and row["size"] in (1, 40)
        )
        require(
            type(row["raw_utf8"]) is str
            and 0 < len(row["raw_utf8"].encode("utf8")) <= 65536
        )
        require(
            hashlib.sha256(row["raw_utf8"].encode("utf8")).hexdigest()
            == row["payload_sha256"]
        )
        require(
            row["origin"] in ("RETAINED_PUBLIC_BODY", "MANUALLY_INVENTED_PUBLIC_BODY")
        )
        key = row["fixture_id"], row["size"]
        require(key not in keys)
        keys.add(key)
    return data


def validate_workloads(data):
    """Exact existing public corpus, AP2 contracts and cumulative T3 reservation."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as a
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix

    campaign = data["configuration"]["campaigns"]
    indices = (0, 9, 10, 0)
    wanted = set()
    rows_bound = ordinals = events = selected_bytes = 0
    cuts = 9
    for index, (item, phase) in enumerate(zip(campaign, data["phases"], strict=True)):
        profile, plan = item["profile"], item["plan"]
        a.validate_plan(plan, profile)
        a.validate(phase["start"], a.START)
        a.verify_work_manifest(lambda: iter(item["work"]), plan)
        expected, controls = matrix.work_for(
            indices[index], profile["transport_profile_sha256"]
        )
        if index == 3:
            expected = expected[:3]
        require(item["work"] == expected and plan["control_recipes"] == controls)
        require(
            profile["states"][0]["connections"] == 2
            and profile["states"][0]["admitted_operations"] == 2
            and len(profile["states"]) == 1
        )
        require(profile["monitoring"]["mode"] == "PUBLIC_GAPS_ONLY")
        require(plan["shutdown_reserve_ms"] == 80000)
        require(
            profile["policy_freeze_record_sha256"]
            == data["configuration"]["sources"]["policy_freeze"]
        )
        start = phase["start"]
        require(
            start["sampling_policy_sha256"] == a.POLICY_SHA
            and start["rule_bundle_sha256"] == a.RULE_BUNDLE
        )
        require(
            start["policy_freeze_record_sha256"]
            == profile["policy_freeze_record_sha256"]
        )
        if index < 2:
            wanted.update(
                (work["fixture_id"], work["result_limit"]) for work in expected
            )
        maximum = plan["sampling_budget"]["maximum_observations"]
        attempts = (
            plan["budgets"]["data_attempts"] + plan["budgets"]["control_http_attempts"]
        )
        rows_bound += maximum + attempts + 16
        ordinals += attempts
        events += plan["budgets"]["event_count"]
        selected_bytes += plan["budgets"]["storage_bytes"]
        cuts += (plan["budgets"]["active_duration_ms"] + 4999) // 5000
    require(wanted == {(row["fixture_id"], row["size"]) for row in data["responses"]})
    require(rows_bound // 56 + cuts + 1 <= 1500, "AP2_DIAGNOSTIC_TIMING_RESERVATION")
    require(
        events
        + 24 * ordinals
        + 128 * 4
        + 128
        + 1501
        + data["limits"]["native_helper_creation_reserve"]
        <= data["limits"]["maximum_creations"],
        "AP2_DIAGNOSTIC_CREATION_RESERVATION",
    )
    require(
        selected_bytes
        # Existing os.write instrumentation conservatively also charges the
        # independent timing writer and instrumented helper writes.
        + 2 * 1500 * 32768
        + 2**20
        + 2 * data["limits"]["native_helper_bytes_reserve"]
        <= data["limits"]["maximum_bytes"],
        "AP2_DIAGNOSTIC_BYTE_RESERVATION",
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_response as validation,
    )

    require(
        data["configuration"]["public_validation_sha256"]
        == digest(validation.descriptor(validation.CORPUS_VERSION))
    )
    require(
        data["limits"]["native_helper_bytes_reserve"] >= 128 * 2**20
        and data["limits"]["native_helper_creation_reserve"] >= 64
    )


def open_allowed(path, *, write, source, output, input_path, evidence):
    """Pure audit policy. Kernel/library allowances contain no protected inputs."""
    path = Path(os.path.realpath(os.fsdecode(path)))
    if any(
        part in {".ssh", ".config", "credentials", ".git"} or part.startswith(".env")
        for part in path.parts
    ):
        return False
    output = Path(output)
    if write:
        return path == output or path.is_relative_to(output)
    safe = (
        source / "src",
        source / "scripts",
        source / "docs/scientific_assets",
        source / "tests",
        source / "cluster",
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        evidence,
    )
    if (
        path == input_path
        or path == output
        or path.is_relative_to(output)
        or any(path == root or path.is_relative_to(root) for root in safe)
    ):
        return True
    kernel_files = {
        "/proc/self/cgroup",
        "/proc/self/status",
        "/proc/self/mountinfo",
        "/proc/sys/kernel/random/boot_id",
        "/proc/meminfo",
        "/dev/null",
        "/dev/urandom",
    }
    return str(path) in kernel_files or path.is_relative_to("/sys/fs/cgroup")


def build_live_authority(data, bundle, review, review_hash, source, source_sha, clock):
    """Own diagnostic envelope; genuine inherited M2 resolver and kernel facts.

    Public runtime configuration v2 keeps its full-matrix interpretation. This
    representative family binds a separate closed review/configuration scope.
    No memory record, kernel fact or allowance is fabricated or substituted.
    """
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_wf_ap2_assurance as assurance,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

    class DiagnosticRuntimeAuthority(runtime.Authority):
        def __init__(self):
            self.config, self.bundle, self.review, self.review_hash = (
                data["configuration"],
                bundle,
                review,
                review_hash,
            )
            self.clock, self.git_sha, self.active, self.start = (
                clock,
                source_sha,
                None,
                None,
            )
            self.test_only = False
            self._enforcement_lock = threading.Lock()
            self._enforcement_checks = self._runtime_inventory_checks = 0
            self._runtime_inventory_limit = None
            self.configuration_scope_sha256 = assurance.configuration_scope(self.config)
            require(
                type(review) is dict
                and set(review)
                == {
                    "version",
                    "scope",
                    "disposition",
                    "configuration_sha256",
                    "report_sha256",
                    "source_files",
                    "sampling_evidence",
                }
            )
            require(
                review["version"] == REVIEW_VERSION
                and review["scope"] == SCOPE
                and review["disposition"] == "PASS"
            )
            require(review["configuration_sha256"] == digest(self.config))
            require(
                hashlib.sha256(io.read(bundle / "integration_review.md")).hexdigest()
                == review["report_sha256"]
            )
            require(
                type(review["source_files"]) is list
                and 1 <= len(review["source_files"]) <= 128
            )
            for entry in review["source_files"]:
                require(
                    type(entry) is dict
                    and set(entry) == {"path", "sha256"}
                    and hash_value(entry["sha256"])
                )
                path = Path(entry["path"])
                require(not path.is_absolute() and ".." not in path.parts)
                require(
                    hashlib.sha256((source / path).read_bytes()).hexdigest()
                    == entry["sha256"]
                )
            self.recheck()

        def require(self, purpose, identity, context):
            if purpose == "control_recipe":
                from safe_geocoding_pipeline.preprocessing.stages import (
                    s12_public_matrix as matrix,
                )

                self.recheck()
                require(self.active is not None and self.start is not None)
                item, plan = self.active
                require(
                    identity == digest(matrix.check_descriptor())
                    and context in plan["control_recipes"]
                )
                require(
                    self.start["client_git_sha"] == self.git_sha
                    and self.start["profile_sha256"] == digest(item["profile"])
                    and self.start["plan_sha256"] == digest(plan)
                )
                return
            return super().require(purpose, identity, context)

    return DiagnosticRuntimeAuthority()


def install_denials(source, output, input_path, evidence):
    """Reuse the existing process network guard and Python audit/provider denial.

    The returned native guard label is earned only by the actual guard call.
    Python path/provider denial is not described as native filesystem isolation.
    """
    spec = importlib.util.spec_from_file_location(
        "ap2_existing_guard", source / "scripts/stage12_scale120_diagnostic.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    network = guard.deny_linux_network()

    def denied(*args, **kwargs):
        raise PermissionError("AP2_DIAGNOSTIC_ACCESS_DENIED")

    creations = [0]
    selected_limit = [None]
    lock = threading.Lock()

    def audit(event, values):
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in ("os.system", "os.fork", "os.posix_spawn"):
            denied()
        if event == "open" and isinstance(values[0], (str, bytes)):
            flags = values[2] if type(values[2]) is int else 0
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if not open_allowed(
                values[0],
                write=write,
                source=source,
                output=output,
                input_path=input_path,
                evidence=evidence,
            ):
                denied()
            if flags & os.O_CREAT:
                charge(1)
        elif event == "os.mkdir":
            if not open_allowed(
                values[0],
                write=True,
                source=source,
                output=output,
                input_path=input_path,
                evidence=evidence,
            ):
                denied()
            charge(1)
        elif (
            event in ("os.listdir", "os.scandir")
            and values
            and isinstance(values[0], (str, bytes))
        ):
            if not open_allowed(
                values[0],
                write=False,
                source=source,
                output=output,
                input_path=input_path,
                evidence=evidence,
            ):
                denied()

    def charge(amount):
        with lock:
            creations[0] += amount
            require(
                selected_limit[0] is not None and creations[0] <= selected_limit[0],
                "AP2_DIAGNOSTIC_CREATION_LIMIT",
            )

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        setattr(socket.socket, name, denied)
    for name in ("Popen", "run", "call", "check_output", "check_call"):
        setattr(subprocess, name, denied)
    sys.addaudithook(audit)
    return guard, network, creations, selected_limit, charge, denied


class LiveProofDiagnosticAuthority:
    """Actual RuntimeAuthority M2 resolver; diagnostic grants remain TEST_ONLY."""

    test_only = False  # Never makes a synthetic memory record admissible.
    diagnostic_authority = "TEST_ONLY_NO_SERVICE"

    def __init__(self, authority):
        self.original = authority
        self.clock = authority.clock
        self.configuration_scope_sha256 = authority.configuration_scope_sha256

    def sampling_bound(self, profile, start):
        record = self.original.sampling_bound(profile, start)
        require(
            record["evidence_origin"] == "LIVE_KERNEL_EVIDENCE",
            "AP2_DIAGNOSTIC_LIVE_M2_REQUIRED",
        )
        return record

    def enforcement_facts(self, record):
        require(
            record["evidence_origin"] == "LIVE_KERNEL_EVIDENCE",
            "AP2_DIAGNOSTIC_LIVE_M2_REQUIRED",
        )
        return self.original.enforcement_facts(record)

    def charge_enforcement_check(self, record):
        return self.original.charge_enforcement_check(record)

    def charge_runtime_inventory_check(self, record):
        return self.original.charge_runtime_inventory_check(record)

    def require(self, purpose, identity, context):
        if purpose == "dispatch":
            from safe_geocoding_pipeline.preprocessing.stages import (
                s12_wf_ap2_assurance as m,
            )

            item, _ = self.original.active
            m.verify_current_facts(
                self.sampling_bound(item["profile"], self.original.start), self
            )
        self.original.require(purpose, identity, context)


def validate_grants(data, bundle):
    """Fresh actual bytes; no grant is synthesized by this execution asset."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

    for role, identity in data["configuration"]["sources"].items():
        raw = io.read(bundle / (role + ".record"), limit=32768)
        require(hashlib.sha256(raw).hexdigest() == identity)
        require(
            io.metadata(raw)
            == {
                "version": "stage12_diagnostic_test_authority_v1",
                "scope": SCOPE,
                "role": role,
                "authority": "TEST_ONLY_NO_SERVICE",
            },
            "AP2_DIAGNOSTIC_AUTHORITY_SCOPE",
        )
    selection = io.metadata(
        io.read(bundle / "diagnostic_selection.record", limit=32768)
    )
    require(digest(selection) == data["selection"]["authority_sha256"])
    require(
        selection
        == {
            "version": "stage12_wf_ap2_diagnostic_selection_v1",
            "scope": SCOPE,
            "status": "ISSUED",
            "input_scope_sha256": input_scope(data),
            "source_sha": data["source_sha"],
            "resource_review_sha256": data["selection"]["resource_review_sha256"],
            "service_authority": False,
        },
        "AP2_DIAGNOSTIC_SELECTION_UNISSUED",
    )
    review = io.metadata(io.read(bundle / "diagnostic_resources.record", limit=32768))
    require(digest(review) == data["selection"]["resource_review_sha256"])
    require(
        review
        == {
            "version": "stage12_wf_ap2_diagnostic_resources_v1",
            "scope": SCOPE,
            "source_sha": data["source_sha"],
            "limits": data["limits"],
            "resources": data["configuration"]["resources"],
            "status": "ISSUED",
            "capacity_entitlement_verified": True,
        },
        "AP2_DIAGNOSTIC_RESOURCE_REVIEW_REQUIRED",
    )


@contextmanager
def instrumentation(check):
    """Existing sole-writer hold hook; it never blocks the sampler/writer thread."""
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_scheduler as scheduler,
    )

    state = dict(current=None, regular=0, role=None, held=False, target=0)
    original_init, original_event, original_call = (
        scheduler.Coordinator.__init__,
        journal.Journal.event,
        journal.Writer.call,
    )

    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        state["current"] = self

    def event(self, kind, body, **kwargs):
        result = original_event(self, kind, body, **kwargs)
        if kind == "RESOURCE_SAMPLE":
            state["role"] = body["observation"]["role"]
        if kind == "SAMPLE_ACK" and state["role"] == "REGULAR":
            state["regular"] += 1
        return result

    def call(self, action, *args, **kwargs):
        current = state["current"]
        if (
            current is not None
            and threading.current_thread() is not self.thread
            and not state["held"]
            and not current.slots
            and getattr(action, "__self__", None) is current.journal
            and getattr(action, "__name__", None) == "verify_storage"
        ):
            while state["regular"] < state["target"]:
                check()
                require(
                    not self.failed.is_set() and current.stop_reason is None,
                    "AP2_DIAGNOSTIC_HOLD_FAILED",
                )
                time.sleep(0.005)
            while True:
                with current.ap_sampler.lock:
                    witnessed = current.ap_sampler.witnessed
                if witnessed >= state["target"]:
                    break
                check()
                require(
                    not self.failed.is_set() and current.stop_reason is None,
                    "AP2_DIAGNOSTIC_HOLD_FAILED",
                )
                time.sleep(0.005)
            state["held"] = True
        return original_call(self, action, *args, **kwargs)

    scheduler.Coordinator.__init__, journal.Journal.event, journal.Writer.call = (
        initialize,
        event,
        call,
    )
    try:
        yield state
    finally:
        scheduler.Coordinator.__init__, journal.Journal.event, journal.Writer.call = (
            original_init,
            original_event,
            original_call,
        )


def execute(args, *, started_ns, cpu_started_ns):
    """Only future Goethe invocation; unit tests never execute this campaign."""
    source = args.source.resolve(strict=True)
    sys.path.insert(0, str(source / "src"))
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("WF-AP2 representative denied diagnostic")
    os.umask(0o077)
    require(
        args.evidence_bundle is not None and hash_value(args.evidence_review_sha256),
        "AP2_DIAGNOSTIC_LIVE_PROOF_REQUIRED",
    )
    bundle = args.evidence_bundle.resolve(strict=True)
    output, input_path = args.output.absolute(), args.input.resolve(strict=True)
    project = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
    controlled = project / "derived/controlled/stage12/client_diagnostics"
    require(
        source.parent == project / "integration_stage12"
        and output.parent == controlled
        and input_path.parent == controlled
        and bundle.parent == controlled,
        "AP2_DIAGNOSTIC_PATH_SCOPE",
    )
    require(
        not output.exists()
        and Path(__file__).resolve() == source / "scripts/stage12_wf_ap2_diagnostic.py"
    )
    guard, network_guard, creations, creation_limit, charge_entries, denied = (
        install_denials(source, output, input_path, bundle)
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport

    transport.Secret.runtime = transport.Secret.private_file = denied
    # Provider/path/network denial is active BEFORE opening any input payload.
    with input_path.open("rb") as stream:
        raw = stream.read(64 * 2**20 + 1)
    require(
        len(raw) <= 64 * 2**20 and hashlib.sha256(raw).hexdigest() == args.input_sha256
    )
    data = json.loads(raw)
    require(canonical(data) == raw)
    validate_envelope(data, args.source_sha, for_execution=True)
    require(
        data["configuration"]["command_paths"]
        == {
            "source": str(source),
            "input": str(input_path),
            "output": str(output),
            "evidence_bundle": str(bundle),
        },
        "AP2_DIAGNOSTIC_PATH_SCOPE",
    )
    limits = data["limits"]
    require(len(raw) <= limits["maximum_input_bytes"])
    creation_limit[0] = limits["maximum_creations"]
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_wf_ap2_assurance as assurance,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as ap
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_response as validation,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_sampling as sampling,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operational_audit as oa,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as storage
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli

    transport.Secret.runtime = transport.Secret.private_file = denied
    runtime.verify_successor_assets(source)
    require(
        (source / "docs/scientific_assets" / (VERSION + ".json")).read_bytes()
        == canonical(descriptor()),
        "AP2_DIAGNOSTIC_DESCRIPTOR_CHANGED",
    )
    validate_grants(data, bundle)
    config, clock = data["configuration"], runtime.Clock()
    review_raw = storage.read(bundle / "integration_review.binding.json", limit=65536)
    require(hashlib.sha256(review_raw).hexdigest() == args.evidence_review_sha256)
    original = build_live_authority(
        data,
        bundle,
        storage.metadata(review_raw),
        args.evidence_review_sha256,
        source,
        args.source_sha,
        clock,
    )
    authority = LiveProofDiagnosticAuthority(original)
    for item, phase in zip(config["campaigns"], data["phases"], strict=True):
        original.bind(item, item["plan"], phase["start"])
        record = authority.sampling_bound(item["profile"], phase["start"])
        assurance.verify_runtime(
            record,
            authority,
            dict(profile=item["profile"], plan=item["plan"], start=phase["start"]),
        )
    # Only genuine current proof permits public corpus/workload preparation.
    validate_workloads(data)
    original.charge_runtime_inventory_check(original.runtime_inventory_budget())
    actual_runtime = runtime.runtime_inventory(
        config["public_validation_sha256"], successor=True
    )
    require(
        actual_runtime == data["runtime_inventory"], "AP2_DIAGNOSTIC_RUNTIME_CHANGED"
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (limits["maximum_bytes"], limits["maximum_bytes"])
    )
    budget = guard.ArtifactBudget(
        limits["maximum_bytes"] - limits["summary_reserve_bytes"]
    )
    guard.install_artifact_accounting(storage, journal, budget)
    budget.charge(limits["native_helper_bytes_reserve"])
    charge_entries(limits["native_helper_creation_reserve"])
    storage.reserve(output)
    deadline = started_ns + limits["seconds"] * 10**9

    def check():
        require(clock.now_ns() < deadline, "AP2_DIAGNOSTIC_DEADLINE")
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        require(
            rss * (1 if sys.platform == "darwin" else 1024) <= limits["rss_bytes"],
            "AP2_DIAGNOSTIC_RSS_LIMIT",
        )
        require(not budget.snapshot()["exceeded"])

    observer = timing.SamplingTiming(
        output / "public_path_timing",
        phase_count=4,
        timing_schema=cp.WF_SCHEMA,
        timing_policy_version=ap.POLICY_VERSION,
        timing_binding=dict(
            policy_sha256=ap.POLICY_SHA,
            source_sha256=digest(data["source_sha"]),
            task_sha256=args.input_sha256,
        ),
        phase_windows=[
            dict(phase_id=i, selected_phase_ms=entry[1])
            for i, entry in enumerate(PHASES, 1)
        ],
        cumulative_deadline_ns=deadline,
        clock_ns=clock.now_ns,
        budget_charge=budget.charge,
    )
    resource_spec = importlib.util.spec_from_file_location(
        "ap2_existing_resource_observer",
        source / "scripts/stage12_resource_characterization.py",
    )
    resource_module = importlib.util.module_from_spec(resource_spec)
    resource_spec.loader.exec_module(resource_module)
    check()
    resource_observation = resource_module.characterize(output / "resource")
    check()
    bodies = {
        (row["fixture_id"], row["size"]): row["raw_utf8"].encode("utf8")
        for row in data["responses"]
    }
    control_raw = canonical(
        {
            "type": "FeatureCollection",
            "features": [],
            "geocoding": {"version": "TEST_ONLY"},
        }
    )
    attempts, phases, failure = 0, [], None
    negative_ready = threading.Event()
    attempts_lock = threading.Lock()
    negative_starts = 0

    def dispatch(work, target, hooks):
        nonlocal attempts, negative_starts
        check()
        with attempts_lock:
            attempts += 1
            require(attempts <= 107, "AP2_DIAGNOSTIC_ATTEMPT_LIMIT")
            if current_label == "malformed":
                negative_starts += 1
                if negative_starts >= 2:
                    negative_ready.set()
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, check)
        if current_label == "malformed":
            while not negative_ready.wait(0.005):
                check()
            payload = b"{broken"
        else:
            time.sleep(0.005)
            payload = (
                control_raw
                if work["kind"] == "SERVICE_CONTROL"
                else bodies[work["fixture_id"], work["result_limit"]]
            )
        result = transport.Capture(
            "VALIDATION_REQUIRED",
            "OK",
            200,
            "application/json",
            "identity",
            None,
            payload,
            len(payload),
            5,
        )
        hooks.completed(result)
        return result

    adapter = validation.Validation(validation.CORPUS_VERSION)
    try:
        with instrumentation(check) as state:
            for phase_id, (item, phase) in enumerate(
                zip(config["campaigns"], data["phases"], strict=True), 1
            ):
                check()
                current_label = item["label"]
                state.update(
                    current=None,
                    regular=0,
                    role=None,
                    held=False,
                    target=phase["hold_regular_acks"],
                )
                profile, plan, start = item["profile"], item["plan"], phase["start"]
                original.bind(item, plan, start)
                phase_deadline = min(
                    deadline,
                    clock.now_ns() + plan["budgets"]["active_duration_ms"] * 10**6,
                )
                observer.phase_open(
                    phase_id,
                    phase_deadline_ns=phase_deadline,
                    timeout_seconds=min(5, (deadline - clock.now_ns()) / 1e9),
                )
                root = output / current_label
                report = cli.run_operations_block(
                    profile,
                    plan,
                    start,
                    work_factory=lambda: iter(item["work"]),
                    output=root,
                    block_id=1,
                    authority=authority,
                    clock=clock,
                    dispatch=dispatch,
                    runtime_inventory=actual_runtime,
                    runtime_key=b"DIAGNOSTIC_TEST_ONLY",
                    control_adapters=matrix.adapters(plan),
                    monitor=None,
                    free_bytes=lambda: runtime.filesystem_free_bytes(output),
                    segment_authority=config["sources"]["owner"],
                    writer_exclusion_evidence=config["sources"]["owner"],
                    epoch=phase["epoch_id"],
                    writer_release_evidence=config["sources"]["owner"],
                    public_validation=adapter,
                    timing_observer=observer,
                    task_deadline_ns=phase_deadline,
                )
                summaries = sampling.inspect(
                    lambda: journal.read_events(root, ap.digest(start), contract=ap),
                    profile,
                    start,
                    maximum_segments=1,
                    contract=ap,
                )
                require(
                    summaries and all(row["complete"] for row in summaries),
                    "AP2_DIAGNOSTIC_SAMPLING_INCOMPLETE",
                )
                observer.phase_close(
                    phase_id,
                    quiescent=True,
                    timeout_seconds=min(5, (deadline - clock.now_ns()) / 1e9),
                )
                require(state["regular"] >= phase["hold_regular_acks"])
                if current_label != "malformed":
                    require(
                        report["report_complete"]
                        and report["disposition"] == "COMPLETED"
                    )
                    block = runtime.reopen_completed(
                        root,
                        profile,
                        plan,
                        start,
                        validation_sha256=config["public_validation_sha256"],
                        control_adapters=matrix.adapters(plan),
                    )
                    require(block == report["blocks"][0])
                    if current_label == "controls8":
                        require(len(matrix.verify_controls(root, plan)) == 4)
                else:
                    require(
                        not report["report_complete"]
                        and report["disposition"] == "STOPPED"
                        and 2 <= negative_starts <= 3
                    )
                    try:
                        runtime.reopen_completed(
                            root,
                            profile,
                            plan,
                            start,
                            validation_sha256=config["public_validation_sha256"],
                        )
                    except ap.c.Stage12Error:
                        pass
                    else:
                        require(False, "AP2_DIAGNOSTIC_NEGATIVE_ADOPTED")
                    for event in journal.read_events(
                        root, ap.digest(start), contract=ap
                    ):
                        if event["kind"] == "ATTEMPT_FINALIZED":
                            work = item["work"][event["body"]["work_id"] - 1]
                            name = audit.name_for(
                                work["work_id"], event["body"]["attempt"]
                            )
                            attempt_root = root / "attempts" / name
                            terminal = audit.reopen(
                                attempt_root,
                                name,
                                validator=adapter.validator(work, attempt_root),
                                context=oa.DataContext(adapter),
                            )
                            require(terminal["outcome"] == "CONTRACT_FAILURE")
                require(
                    (root / "_SEGMENT_SEALED").is_file()
                    and (root / "_WRITER_RELEASED.json").is_file()
                )
                phases.append(
                    dict(
                        label=current_label,
                        report_complete=report["report_complete"],
                        regular_acknowledgements=state["regular"],
                        original_reopen=True,
                    )
                )
                check()
                original.charge_runtime_inventory_check(
                    original.runtime_inventory_budget()
                )
                require(
                    runtime.runtime_inventory(
                        config["public_validation_sha256"], successor=True
                    )
                    == actual_runtime,
                    "AP2_DIAGNOSTIC_RUNTIME_CHANGED",
                )
        require(106 <= attempts <= 107)
    except BaseException:
        failure = "AP2_DIAGNOSTIC_INCOMPLETE"
    finally:
        try:
            summary = observer.close(
                timeout_seconds=min(5, (deadline - clock.now_ns()) / 1e9)
            )
            require(summary["final_timing_coverage_complete"])

            def associate(ordinal, row):
                phase_id = (
                    row["phase_id"]
                    if row["row_kind"] == "PERIODIC_ASYNC"
                    else row["legacy_row"][0]
                )
                require(1 <= phase_id <= 4)
                item = config["campaigns"][phase_id - 1]
                root = output / item["label"]
                sequence = (
                    row["sample_event_seq"]
                    if row["row_kind"] == "PERIODIC_ASYNC"
                    else row["legacy_row"][4]
                )
                event = ap.parse(
                    storage.read(root / "events" / f"{sequence:020d}.json", limit=4096),
                    ap.EVENT,
                )
                ack = (
                    ap.parse(
                        storage.read(
                            root / "events" / f"{row['ack_event_seq']:020d}.json",
                            limit=4096,
                        ),
                        ap.EVENT,
                    )
                    if row["row_kind"] == "PERIODIC_ASYNC"
                    else None
                )
                timing.verify_sampling_association(
                    row, event, phase_id=phase_id, ack_event=ack, contract=ap
                )

            reopened_timing = cp.read_prefix(
                observer.checkpoints.root,
                expected_binding=summary["checkpoint"]["timing_binding"],
                expected_snapshot=summary["checkpoint"],
                record_consumer=associate,
            )
            require(
                not reopened_timing["incomplete"], "AP2_DIAGNOSTIC_TIMING_INCOMPLETE"
            )
        except BaseException:
            summary = observer.snapshot()
            failure = failure or "AP2_DIAGNOSTIC_TIMING_INCOMPLETE"
    result = dict(
        version=VERSION,
        scope=SCOPE,
        source_sha=args.source_sha,
        input_sha256=args.input_sha256,
        complete=failure is None and len(phases) == 4,
        error=failure,
        attempts=attempts,
        expected_attempts=106,
        maximum_attempts=107,
        phases=phases,
        timing=summary,
        resource_observation=resource_observation,
        network_guard=network_guard,
        filesystem_guard="PYTHON_AUDIT_PATH_DENIAL_NOT_NATIVE_FILESYSTEM_ISOLATION",
        native_component_bound_claim=False,
        logical_artifact_accounting=budget.snapshot(),
        charged_creation_attempts=creations[0],
        elapsed_ns=clock.now_ns() - started_ns,
        cpu_ns=time.process_time_ns() - cpu_started_ns,
    )
    storage.write(output / "summary.json", canonical(result))
    check()
    signal.alarm(0)
    return 0 if result["complete"] else 1


def descriptor():
    return dict(
        descriptor_version=VERSION,
        configuration_version=CONFIG_VERSION,
        review_binding_version=REVIEW_VERSION,
        scope=SCOPE,
        live_instance=False,
        default_selection_status="UNISSUED_NON_EXECUTABLE",
        explicit_flag="--wf-ap2",
        top_fields=sorted(_TOP),
        required_resource_fields=sorted(_LIMITS),
        configuration_fields=sorted(_CONFIG),
        profile_family="stage12_transport_operations_v4",
        plan_family="stage12_public_characterization_plan_v3",
        start_family="stage12_public_operations_campaign_v3",
        live_memory_record_family="stage12_public_sampling_runtime_bound_v2",
        inherited_m2_purposes=sorted(_M2_PURPOSES),
        phases=[
            dict(
                label=label,
                proposed_phase_ms=duration,
                required_regular_ack_hold=hold,
                planned_work=count,
            )
            for label, duration, hold, count in PHASES
        ],
        proposed_total_seconds=7200,
        expected_attempts=106,
        maximum_attempts=107,
        assurance="LIVE_KERNEL_EVIDENCE_ONLY_WITH_ACTUAL_SHARED_M2_OBSERVER",
        service_authority=False,
        native_component_bound_claim=False,
        input_authority="NO_RECORDS_ISSUED;EXACT_REVIEWED_RESOURCES_AND_WORKLOAD_GRANT_REQUIRED",
    )

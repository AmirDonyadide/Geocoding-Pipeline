"""One reviewed public diagnostic, real adapters and explicit authority gates.

No protected reader, scientific binding, fallback endpoint, synthetic authority
or automatic job resubmission. The existing O-r2 coordinator owns all HTTP work.
"""

from __future__ import annotations
import os
import platform
import resource
import ssl
import subprocess
import threading
import time
import importlib.metadata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from itertools import islice, zip_longest
from . import s12_response as response
from . import s12_assets as assets
from . import s12_operations as v1
from . import s12_public_operations as o
from . import s12_public_response as validation
from . import s12_public_audit as audit
from . import s12_public_operational_audit as oa
from . import s12_public_journal as journal
from . import s12_public_recovery as recovery
from . import s12_public_reporting as reporting
from . import s12_retrieval_contract as c
from . import s12_storage as io
from . import s12_transport as transport
from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

VERSION = "stage12_public_runtime_configuration_v1"
FIELDS = set(
    "version scope task_id output_directory window_start window_end maximum_attempts active_seconds review_wait_seconds transport resources sources campaigns public_validation_sha256".split()
)
OUTPUT_PARENT = Path(
    "/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/public_probe"
)


class Clock:
    def now_ns(self):
        return time.monotonic_ns()

    def utc(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def wait_until(self, ns):
        while (left := ns - self.now_ns()) > 0:
            time.sleep(min(left / 1e9, 0.05))


class Envelope:
    def __init__(self, clock, attempts, seconds):
        o.require(
            type(attempts) is int
            and 0 < attempts <= 400
            and type(seconds) is int
            and 0 < seconds <= 1800
        )
        self.clock = clock
        self.cap = attempts
        self.started = clock.now_ns()
        self.deadline = self.started + seconds * 10**9
        self.attempts = 0
        self.lock = threading.Lock()

    def check(self):
        o.require(self.clock.now_ns() < self.deadline, "S12_PUBLIC_WINDOW_CLOSED")

    def charge(self):
        with self.lock:
            self.check()
            o.require(self.attempts < self.cap, "S12_PUBLIC_ATTEMPT_BUDGET")
            self.attempts += 1

    def wrap(self, hooks):
        owner = self

        class Hooks:
            def started(self, ns):
                hooks.started(ns)

            def signal(self, *args):
                hooks.signal(*args)

            def completed(self, result):
                hooks.completed(result)

            def attempt_deadline_ns(self, started, maximum):
                return min(maximum, owner.deadline)

            def emit(self, write, deadline):
                def check():
                    owner.check()
                    deadline()

                hooks.emit(write, check)

        return Hooks()


def read_object(path):
    return io.metadata(io.read(path, limit=8 * 1024 * 1024))


def validation_for(identity):
    for version in (validation.VERSION, validation.FAMILY_VERSION):
        adapter = validation.Validation(version)
        if o.digest(adapter.descriptor()) == identity:
            return adapter
    raise c.Stage12Error("S12_PUBLIC_VALIDATION_BINDING_INVALID")


def validate_config(config):
    o.require(
        set(config) == FIELDS
        and config["version"] == VERSION
        and config["scope"] == o.SCOPE
    )
    o.validate_type(config["task_id"], "N32")
    for key in ("maximum_attempts", "active_seconds", "review_wait_seconds"):
        o.uint(config[key], True)
    o.require(
        config["maximum_attempts"] == 400
        and 0 < config["active_seconds"] <= 1680
        and 0 < config["review_wait_seconds"] <= 180
    )
    for k in ("window_start", "window_end"):
        o.validate_type(config[k], "Z")
    o.require(config["window_start"] < config["window_end"])
    validation_for(config["public_validation_sha256"])
    t = config["transport"]
    o.require(
        set(t)
        == {
            "origin",
            "approved_ip",
            "configuration_evidence_sha256",
            "target_limit",
            "header_limit",
        }
    )
    o.require(
        t["origin"] == "https://geocode.safe-frankfurt.de"
        and t["target_limit"] == 4096
        and t["header_limit"] == 16384
    )
    transport.TransportProfile(
        t["origin"],
        t["approved_ip"],
        bytes.fromhex(t["configuration_evidence_sha256"]),
        t["target_limit"],
        t["header_limit"],
    ).validate()
    sources = config["sources"]
    o.require(
        set(sources) == {"owner", "policy_freeze", "operator", "selection", "transport"}
    )
    for value in sources.values():
        o.validate_type(value, "D")
    o.require(
        [x["label"] for x in config["campaigns"]]
        == ["capability_subset", "rate20", "rate40"]
    )
    total = 0
    for item in config["campaigns"]:
        o.require(set(item) == {"label", "profile", "plan", "work", "ascending_sizes"})
        p, plan = item["profile"], item["plan"]
        o.require(type(item["ascending_sizes"]) is bool)
        rate = {"capability_subset": 1, "rate20": 20, "rate40": 40}[item["label"]]
        o.require(
            len(p["states"]) == 1
            and p["states"][0]["rate"] == {"num": rate, "den": 1}
            and len(plan["blocks"]) == 1
            and plan["experiment_kind"] == "PERFORMANCE"
            and item["ascending_sizes"] == (rate == 1)
            and plan["blocks"][0]["evaluation"]
            == ("EXPLORATORY" if rate == 1 else "CONFIRMATORY")
        )
        o.require(
            p["resources"] == config["resources"]
            and p["monitoring"]["mode"] == "PUBLIC_GAPS_ONLY"
        )
        # Confirmatory templates are validated after binding the actual reviewed
        # partial parent; no made-up content hash is supplied for that evidence.
        check = deepcopy(plan)
        if item["label"] != "capability_subset":
            o.require(check["capability_parent_sha256"] is None)
            criteria = plan["blocks"][0]["criteria"]
            o.validate_type(criteria, "Criteria")
            budget = plan["blocks"][0]["budget"]
            state, resources = p["states"][0], p["resources"]
            o.require(
                criteria["min_duration_ms"]
                <= criteria["max_duration_ms"]
                <= budget["active_duration_ms"]
                and criteria["min_valid_data"] <= budget["data_observations"]
                and o.rate_le(criteria["min_attempt_rate"], state["rate"])
                and o.rate_le(criteria["min_durable_data_rate"], state["rate"])
                and criteria["max_pending_count"] <= 2 * state["admitted_operations"]
                and criteria["max_pending_bytes"] <= resources["pending_request_bytes"]
                and criteria["max_reserved_bytes"]
                <= resources["admission_memory_bytes"]
            )
            cells = [(x["mode"], x["size"]) for x in criteria["required_cells"]]
            o.require(
                cells == sorted(set(cells)) and all(size <= 40 for _, size in cells)
            )
            check["blocks"][0]["criteria"] = None
            check["blocks"][0]["evaluation"] = "EXPLORATORY"
        o.validate_plan(check, p)
        o.verify_work_manifest(lambda: iter(item["work"]), plan)
        total += (
            plan["budgets"]["data_attempts"] + plan["budgets"]["control_http_attempts"]
        )
        o.require(
            not plan["control_recipes"]
            and all(w["kind"] == "DATA" for w in item["work"])
        )
        o.require(
            plan["window_start"] == config["window_start"]
            and plan["window_end"] == config["window_end"]
        )
        o.require(
            p["resources"]["admission_memory_bytes"] == o.MEMORY
            and all(
                s["admitted_operations"] <= 2
                and s["connections"] <= 2
                and s["rate"]["num"] <= 40 * s["rate"]["den"]
                for s in p["states"]
            )
        )
    o.require(total <= 400)


def runtime_inventory(validation_sha256=None):
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "openssl": ssl.OPENSSL_VERSION,
        "packages": sorted(
            (d.metadata["Name"], d.version) for d in importlib.metadata.distributions()
        ),
        "public_validation_sha256": validation_sha256
        or o.digest(validation.descriptor()),
        "scientific_identity_verified": False,
        "job_id": os.environ["SLURM_JOB_ID"],
        "resource_sampling_is_service_monitoring": False,
    }


class Authority:
    """Resolve actual pinned records and their reviewed exact applicability.

    The caller pins the independently reviewed binding file. It is not a digital
    signature, a self-issued operator attestation, or arbitrary hash allow-all.
    """

    def __init__(self, config, bundle, review, review_hash, repository, git_sha, clock):
        self.config, self.bundle, self.review, self.review_hash = (
            config,
            bundle,
            review,
            review_hash,
        )
        self.clock = clock
        self.git_sha = git_sha
        self.active = None
        self.start = None
        o.require(
            set(review)
            == {
                "version",
                "disposition",
                "configuration_sha256",
                "report_sha256",
                "source_files",
                "scope",
            }
        )
        o.require(
            review["version"] == "stage12_public_integration_review_binding_v1"
            and review["disposition"] == "PASS"
            and review["scope"] == o.SCOPE
        )
        o.require(review["configuration_sha256"] == o.digest(config))
        o.require(
            c.sha(io.read(bundle / "integration_review.md")).hex()
            == review["report_sha256"]
        )
        for entry in review["source_files"]:
            o.require(
                set(entry) == {"path", "sha256"}
                and not Path(entry["path"]).is_absolute()
                and ".." not in Path(entry["path"]).parts
            )
            o.require(
                c.sha((repository / entry["path"]).read_bytes()).hex()
                == entry["sha256"],
                "PUBLIC_PROBE_EXECUTABLE_MISMATCH",
            )
        self.recheck()

    def recheck(self):
        o.require(
            self.config["window_start"] <= self.clock.utc() < self.config["window_end"],
            "S12_PUBLIC_WINDOW_CLOSED",
        )
        for role, h in self.config["sources"].items():
            o.require(
                c.sha(io.read(self.bundle / (role + ".record"))).hex() == h,
                "S12_PUBLIC_AUTHORITY_CHANGED",
            )

    def bind(self, item, plan, start):
        self.active = (item, plan)
        self.start = start

    def require(self, purpose, evidence_sha256, context):
        self.recheck()
        o.require(
            self.active is not None and self.start is not None,
            "S12_PUBLIC_AUTHORITY_UNBOUND",
        )
        item, plan = self.active
        profile = item["profile"]
        sources = self.config["sources"]
        hashes = {
            "policy_freeze_record_sha256": sources["policy_freeze"],
            "implementation_authorization_sha256": sources["owner"],
            "implementation_review_sha256": self.review_hash,
            "initial_workload_authority_sha256": sources["owner"],
            "operator_allowance": sources["operator"],
            "transport_profile": o.digest(self.config["transport"]),
            "plan_selection": sources["selection"],
            "rate_state": sources["selection"],
            "resources": sources["selection"],
            "monitoring": sources["selection"],
            "segment_open": sources["owner"],
            "writer_exclusion": sources["owner"],
            "runtime_preflight": sources["owner"],
            "writer_release": sources["owner"],
            "dispatch": sources["owner"],
        }
        o.require(
            purpose in hashes and evidence_sha256 == hashes[purpose],
            "S12_PUBLIC_AUTHORITY_SCOPE",
        )
        # Every supplied context must match this one exact selected campaign.
        for k, v in (("profile", profile), ("plan", plan), ("start", self.start)):
            if k in context:
                o.require(context[k] == v, "S12_PUBLIC_AUTHORITY_SCOPE")
        if purpose == "transport_profile" or purpose == "operator_allowance":
            o.require(context == profile)
        if purpose == "plan_selection":
            o.require(context == plan)
        if purpose == "rate_state":
            o.require(context in profile["states"])
        if purpose == "resources":
            o.require(context == profile["resources"])
        if purpose == "monitoring":
            o.require(context == profile["monitoring"])
        if purpose == "dispatch":
            o.require(set(context) == {"work", "attempt", "state"})
            o.uint(context["attempt"], True)
            o.require(
                context["attempt"] <= 5
                and context["work"] in item["work"]
                and context["state"] in profile["states"],
                "S12_PUBLIC_AUTHORITY_SCOPE",
            )
        if purpose in ("segment_open", "writer_exclusion"):
            o.require(context == {"start": self.start, "block": plan["blocks"][0]})
        o.require(
            self.start["client_git_sha"] == self.git_sha
            and self.start["profile_sha256"] == o.digest(profile)
            and self.start["plan_sha256"] == o.digest(plan)
        )


def reopen_completed(root, profile, plan, start, *, validation_sha256=None):
    """Existing event/receipt/ledger/report readers, no trusted aggregate shortcut."""
    io._checkpoint()
    root_info = root.stat(follow_symlinks=False)
    root_identity = (root.resolve(), root_info.st_dev, root_info.st_ino)
    adapter = validation_for(validation_sha256 or o.digest(validation.descriptor()))

    def works():
        return iter(plan_work(root, plan))

    projection = None

    def events():
        return (
            projection.events()
            if projection is not None
            else journal.read_events(root, o.digest(start))
        )

    def receipt(work, event):
        name = audit.name_for(work["work_id"], event["attempt"])
        path = root / "attempts" / name
        o.require(
            c.sha(io.read(path / (name + "_receipt.json"))).hex()
            == event["receipt_inventory_sha256"]
        )
        return audit.reopen(
            path,
            name,
            validator=adapter.validator(work, path),
            context=oa.DataContext(adapter),
        )

    o.require(io.read(root / "campaign_start.json") == c.canonical(start))
    o.require(
        start["profile_sha256"] == o.digest(profile)
        and start["plan_sha256"] == o.digest(plan)
    )
    o.verify_work_manifest(works, plan)
    snapshot_raw = io.read(root / "snapshot.json")
    snapshot = o.parse(snapshot_raw, o.SNAPSHOT)
    campaign_raw = io.read(root / "campaign_report.json")
    campaign = o.parse(campaign_raw, o.REPORT)
    o.require(
        snapshot["disposition"] == "COMPLETED"
        and io.read(root / "_SEGMENT_SEALED", limit=0) == b""
    )
    o.require(
        read_object(root / "_WRITER_RELEASED.json")
        == {
            "writer_release_evidence_sha256": snapshot[
                "writer_release_evidence_sha256"
            ],
            "snapshot_sha256": o.digest(snapshot),
        }
    )
    for area in ("events", "attempts"):
        o.require(
            o.manifest_digest(journal.evidence_inventory(root, area))
            == snapshot[area[:-1] + "_inventory_sha256"]
        )
    block = read_object(root / "block_report.json")
    o.validate_type(block, "BlockReport")
    if (root / "measurement_event_prefix.json").exists():
        projection = journal.MeasurementPrefix.from_closed(
            root, o.digest(start), block["input_last_event_seq"], check=io._checkpoint
        )
    state = recovery.replay(events())
    o.require(
        state["closed"] and not state["unfinished"] and state["breaker_reason"] is None
    )
    o.require(o.digest(state["last_event"]) == snapshot["last_event_sha256"])
    for calculated, retained in zip_longest(
        recovery.work_ledger(works, events, receipt),
        journal.read_array(root / "work_ledger.json"),
    ):
        o.require(
            calculated == retained
            and calculated is not None
            and calculated["state"] == "DURABLE_SUCCESS"
        )
    block = read_object(root / "block_report.json")
    o.validate_type(block, "BlockReport")
    comparisons = list(journal.read_array(root / "repeat_comparison.json"))

    # Raw bytes and their exact structural repeat relation are checked anew.
    def structural(work, final):
        o.require(final is not None)
        terminal = receipt(work, final)
        name = audit.name_for(work["work_id"], final["attempt"])
        path = root / "attempts" / name
        raw = response.decompress(
            io.read(path / (name + ".zst")),
            length=terminal["application_payload_bytes"],
            expected_hash=bytes.fromhex(terminal["response_sha256"]),
        )
        return validation.shapes(raw, work, version=adapter.VERSION)

    def pairs():
        for work in works():
            prior = next(
                (
                    w
                    for w in works()
                    if w["work_id"] < work["work_id"]
                    and (w["fixture_id"], w["result_limit"])
                    == (work["fixture_id"], work["result_limit"])
                ),
                None,
            )
            if prior is not None:
                yield prior, work

    expected_comparisons = 0
    pair_rows = iter(pairs())
    while batch := list(islice(pair_rows, 4)):
        # Same bounded metadata join as capture-side comparisons. Consume the
        # entire validated prefix; every receipt/body still reopens per pair.
        ids = {w["work_id"] for pair in batch for w in pair}
        finals = {}
        for event in events():
            body = event["body"]
            if (
                event["kind"] == "ATTEMPT_FINALIZED"
                and body["work_id"] in ids
                and body["outcome"]["value"] in c.SUCCESS
            ):
                o.require(body["work_id"] not in finals)
                finals[body["work_id"]] = body
        for prior, work in batch:
            expected_comparisons += 1
            value = next(
                (x for x in comparisons if x["next_work_id"] == work["work_id"]), None
            )
            o.require(
                value
                == {
                    "first_work_id": prior["work_id"],
                    "next_work_id": work["work_id"],
                    "equal": structural(prior, finals.get(prior["work_id"]))
                    == structural(work, finals.get(work["work_id"])),
                }
            )
    o.require(len(comparisons) == expected_comparisons)

    def before():
        return (e for e in events() if e["seq"] <= block["input_last_event_seq"])

    recomputed = reporting.block_report(
        plan,
        profile,
        1,
        events=before,
        works=works,
        verified_receipt=receipt,
        repeat_evidence=lambda: (
            c.sha(io.read(root / "repeat_comparison.json")).hex(),
            all(x["equal"] for x in comparisons),
        ),
        monitoring_closed=lambda: True,
    )
    o.require(recomputed == block)
    closed = [e for e in events() if e["kind"] == "BLOCK_CLOSED"]
    o.require(
        len(closed) == 1 and closed[0]["body"]["report_sha256"] == o.digest(block)
    )
    if projection is not None:
        projection.verify_original()
    recovery.snapshot_evidence(
        root,
        snapshot,
        state,
        closed[0]["body"]["report_sha256"],
        check=io._checkpoint,
    )
    o.require(
        next(
            journal.read_array(
                root / "remaining_work_ledger.json", check=io._checkpoint
            ),
            None,
        )
        is None
    )
    expected_campaign = reporting.campaign_report(
        start,
        event_inventory_sha256=snapshot["event_inventory_sha256"],
        attempt_inventory_sha256=snapshot["attempt_inventory_sha256"],
        snapshots=[o.digest(snapshot)],
        blocks=[block],
        disposition="COMPLETED",
        scientific_identity_verified=False,
        reconciliation_reasons=[],
        plan=plan,
    )
    o.require(campaign == expected_campaign and campaign["report_complete"])
    o.require(
        journal.tree_bytes(
            root,
            frozenset(
                {
                    "snapshot.json",
                    "_SEGMENT_SEALED",
                    "campaign_report.json",
                    "_WRITER_RELEASED.json",
                }
            ),
            check=io._checkpoint,
        )
        == snapshot["controller"]["stored_bytes"]
    )
    o.verify_work_manifest(works, plan)
    o.require(io.read(root / "snapshot.json") == snapshot_raw)
    o.require(io.read(root / "campaign_report.json") == campaign_raw)
    o.require(io.read(root / "campaign_start.json") == c.canonical(start))
    after = root.stat(follow_symlinks=False)
    o.require((root.resolve(), after.st_dev, after.st_ino) == root_identity)
    io._checkpoint()
    return block


def plan_work(root, plan):
    for i in range(1, plan["budgets"]["data_observations"] + 1):
        yield read_object(root / "work" / f"{i:020d}.json")


def qualifies(block, *, smoke=False, advance40=False):
    expected = "EXPLORATORY_ONLY" if smoke else "PASS"
    if block["reasons"] != (["EXPLORATORY_NO_QUALIFICATION"] if smoke else []):
        return False
    if block["status"] != expected or not all(
        block[k]
        for k in (
            "monitoring_complete",
            "receipts_complete",
            "resource_sampling_complete",
        )
    ):
        return False
    for name in (
        "unprocessed_data",
        "durable_retryable",
        "durable_terminal_failure",
        "unknown_delivery",
        "retry_attempt_starts",
        "cooldown_events",
        "downshift_events",
        "breakers",
    ):
        if block["counts"][name]["value"] != 0:
            return False
    if advance40:
        stat = block["latencies"]["full_slot_data"]["p95_ms"]
        return (
            stat is not None
            and stat <= 50
            and block["peaks"]["writer_wait_ms"] is not None
            and block["peaks"]["writer_wait_ms"] <= 25
        )
    return True


def progression(root, label, block, clock, envelope, seconds):
    """No automatic reviewed disposition: wait for the actual non-author review."""
    expected = {
        "version": "stage12_public_progression_review_v1",
        "scope": o.SCOPE,
        "task_root": str(root),
        "prior_label": label,
        "prior_block_report_sha256": o.digest(block),
        "next_rate": 20 if label == "capability_subset" else 40,
        "reviewer": "/root/public_followup_review",
        "disposition": "PASS",
    }
    io.write(root / (label + "_AWAITING_REVIEW.json"), c.canonical(expected))
    deadline = min(envelope.deadline, clock.now_ns() + seconds * 10**9)
    path = root / (label + "_review.json")
    while clock.now_ns() < deadline:
        if path.exists():
            value = read_object(path)
            o.require(
                set(value) == set(expected) | {"review_report_sha256"},
                "S12_PUBLIC_PROGRESSION_REVIEW_INVALID",
            )
            o.require(
                {k: value[k] for k in expected} == expected,
                "S12_PUBLIC_PROGRESSION_REVIEW_INVALID",
            )
            o.require(
                c.sha(io.read(root / (label + "_review.md"))).hex()
                == value["review_report_sha256"],
                "S12_PUBLIC_PROGRESSION_REVIEW_INVALID",
            )
            return value
        clock.wait_until(min(deadline, clock.now_ns() + 1_000_000_000))
    raise c.Stage12Error("S12_PUBLIC_PROGRESSION_REVIEW_UNAVAILABLE")


def execute(
    config,
    *,
    bundle,
    review,
    review_hash,
    repository,
    git_sha,
    key_provider=transport.Secret.runtime,
    clock=None,
):
    from ..stage12_probe_cli import run_operations_block
    from .s12_public_diagnostics import Failures, classify

    require_goethe_nhr_slurm("stage12 explicit O-r2 public diagnostic")
    validate_config(config)
    clock = clock or Clock()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    assets.verify(repository)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    o.require(
        actual == git_sha
        and len(git_sha) == 40
        and not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repository
        ),
        "PUBLIC_PROBE_EXECUTABLE_MISMATCH",
    )
    authority = Authority(
        config, bundle, review, review_hash, repository, git_sha, clock
    )
    output = Path(config["output_directory"])
    o.require(
        output.parent == OUTPUT_PARENT and output.name == "or2_" + config["task_id"],
        "PUBLIC_PROBE_OUTPUT_SCOPE_INVALID",
    )
    io.reserve(output)  # task-global exclusive reservation, no second invocation/resume
    envelope = Envelope(clock, config["maximum_attempts"], config["active_seconds"])
    io.write(
        output / "_RUN_RESERVED.json",
        c.canonical(
            {
                "task_id": config["task_id"],
                "job_id": os.environ["SLURM_JOB_ID"],
                "configuration_sha256": o.digest(config),
                "review_binding_sha256": review_hash,
                "started_utc": clock.utc(),
            }
        ),
    )
    r = config["resources"]
    mem = os.environ.get("SLURM_MEM_PER_NODE")
    o.require(
        mem is not None and int(mem) * 2**20 >= r["job_memory_bytes"],
        "S12_PUBLIC_MEMORY_ALLOCATION_UNVERIFIED",
    )

    def free():
        stat = os.statvfs(output)
        return stat.f_bavail * stat.f_frsize

    o.require(free() >= r["allocated_disk_bytes"], "S12_PUBLIC_DISK_UNAVAILABLE")
    runtime = runtime_inventory(config["public_validation_sha256"])
    io.write(output / "runtime_inventory.json", c.canonical(runtime))
    io.write(output / "configuration.json", c.canonical(config))
    io.write(output / "review_binding.json", c.canonical(review))
    # The approved provider path is set by the launcher. Never inspect/log value here.
    o.require(
        os.environ.get("SAFE_PELIAS_API_KEY_FILE")
        == str(Path.home() / ".config/safe-geocoding/pelias_api_key")
        and not os.environ.get("SAFE_PELIAS_API_KEY"),
        "PUBLIC_PROBE_AUTH_SOURCE_UNVERIFIED",
    )
    key = key_provider()
    t = config["transport"]
    transport_profile = transport.TransportProfile(
        t["origin"],
        t["approved_ip"],
        bytes.fromhex(t["configuration_evidence_sha256"]),
        t["target_limit"],
        t["header_limit"],
    )

    def dispatch(work, target, hooks):
        envelope.charge()
        authority.recheck()
        return transport.send(
            target, transport_profile, key, v1.Operations(), hooks=envelope.wrap(hooks)
        )

    diagnostics = Failures(clock)
    results = []
    verified_complete = []
    verified_rates = []
    parent = None
    initial_cpu = time.process_time_ns()
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    runtime_operation = "RUNTIME"
    runtime_failure = None
    persistence_failed = False
    try:
        for item in config["campaigns"]:
            runtime_operation = "RUNTIME"
            envelope.check()
            authority.recheck()
            plan = deepcopy(item["plan"])
            if item["label"] != "capability_subset":
                plan["capability_parent_sha256"] = parent
            profile = item["profile"]
            o.validate_plan(plan, profile)
            start = {
                "schema_version": o.START,
                "scope": o.SCOPE,
                "campaign_id": os.urandom(32).hex(),
                "profile_sha256": o.digest(profile),
                "plan_sha256": o.digest(plan),
                "rule_bundle_sha256": o.RULE_BUNDLE,
                "policy_freeze_record_sha256": config["sources"]["policy_freeze"],
                "implementation_authorization_sha256": config["sources"]["owner"],
                "implementation_review_sha256": review_hash,
                "initial_workload_authority_sha256": config["sources"]["owner"],
                "client_git_sha": git_sha,
                "runtime_inventory_sha256": o.digest(runtime),
                "created_utc": clock.utc(),
            }
            authority.bind(item, plan, start)
            phase = output / item["label"]
            source = config["sources"]["owner"]
            phase_deadline = recovery.Deadline(
                clock,
                min(
                    envelope.deadline,
                    clock.now_ns()
                    + min(
                        plan["budgets"]["active_duration_ms"],
                        plan["blocks"][0]["budget"]["active_duration_ms"],
                    )
                    * 1_000_000,
                ),
            )
            result = run_operations_block(
                profile,
                plan,
                start,
                work_factory=lambda: iter(item["work"]),
                output=phase,
                block_id=1,
                authority=authority,
                clock=clock,
                dispatch=dispatch,
                runtime_inventory=runtime,
                runtime_key=key.value,
                control_adapters={},
                monitor=None,
                free_bytes=free,
                segment_authority=source,
                writer_exclusion_evidence=source,
                epoch=os.urandom(32).hex(),
                writer_release_evidence=source,
                public_validation=validation_for(config["public_validation_sha256"]),
                ascending_sizes=item["ascending_sizes"],
                task_deadline_ns=phase_deadline.end_ns,
                diagnostics=diagnostics,
                pause_requested=lambda: (
                    clock.now_ns() >= envelope.deadline - 80 * 10**9
                ),
            )
            results.append(
                {
                    "label": item["label"],
                    "campaign_report_sha256": o.digest(result),
                    "report": result,
                }
            )
            io.write(
                output / (item["label"] + "_result.json"), c.canonical(results[-1])
            )
            if result["disposition"] != "COMPLETED" or not result["report_complete"]:
                break
            runtime_operation = "RUNTIME_REOPEN"
            with io.cooperative_io(phase_deadline.check):
                phase_deadline.check()
                block = reopen_completed(
                    phase,
                    profile,
                    plan,
                    start,
                    validation_sha256=config["public_validation_sha256"],
                )
                phase_deadline.check()
            runtime_operation = "RUNTIME"
            verified_complete.append(item["label"])
            if not qualifies(block, smoke=item["label"] == "capability_subset"):
                break
            if item["label"].startswith("rate"):
                verified_rates.append(int(item["label"][4:]))
            if item["label"] == "rate40":
                break
            if item["label"] == "rate20" and not qualifies(block, advance40=True):
                break
            gate = progression(
                output,
                item["label"],
                block,
                clock,
                envelope,
                config["review_wait_seconds"],
            )
            io.write(
                output / (item["label"] + "_PROGRESSION_ACCEPTED.json"),
                c.canonical(gate),
            )
            if item["label"] == "capability_subset":
                parent = o.digest(block)
    except (Exception, KeyboardInterrupt) as error:
        runtime_failure = error
        diagnostics.record(runtime_operation, error)
        family, code, number = classify(error)
        code = code or "PUBLIC_PROBE_DIAGNOSTIC_STOPPED"
        try:
            io.write(
                output / "diagnostic_stop.json",
                c.canonical({"reason": code, "attempts_charged": envelope.attempts}),
            )
        except (Exception, KeyboardInterrupt) as cleanup:
            persistence_failed = True
            diagnostics.record("CLEANUP", cleanup)
    finally:
        # Supplementary task output, never a campaign seal or writer reuse.
        try:
            io.write(
                output / "failure_diagnostics.json", c.canonical(diagnostics.snapshot())
            )
        except (Exception, KeyboardInterrupt) as cleanup:
            persistence_failed = True
            diagnostics.record("CLEANUP", cleanup)
        summary = {
            "scope": o.SCOPE,
            "scientific_identity_verified": False,
            "continuous_service_state": "NOT_VERIFIED",
            "full_frozen_capability_matrix_completed": False,
            "attempts_dispatched_or_uncertain": envelope.attempts,
            "maximum_attempts": config["maximum_attempts"],
            "elapsed_ns": clock.now_ns() - envelope.started,
            "cpu_ns": time.process_time_ns() - initial_cpu,
            "rss_max_kib_start": rss0,
            "rss_max_kib_end": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_units": "LINUX_KIB_PROCESS_LIFETIME_HIGH_WATER",
            "attempted_phases": [x["label"] for x in results],
            "completed_phases": verified_complete,
            "qualified_public_rates": verified_rates,
            "protected_operating_ceiling_selected": False,
            "C": "UNSELECTED",
            "T": "UNSELECTED",
            "N": "UNSELECTED",
            "failure_diagnostics": diagnostics.snapshot(),
            "diagnostic_persistence_complete": not persistence_failed,
        }
        try:
            io.write(output / "diagnostic_summary.json", c.canonical(summary))
        except (Exception, KeyboardInterrupt) as cleanup:
            diagnostics.record("CLEANUP", cleanup)
            if runtime_failure is not None:
                raise runtime_failure
            raise c.Stage12Error("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED") from None
    if persistence_failed:
        if runtime_failure is not None:
            raise runtime_failure
        raise c.Stage12Error("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
    return summary

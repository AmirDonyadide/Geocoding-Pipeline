"""RA-G1 logical allocation controls over the existing guarded sinks.

Native main/spill controls retain their exact scope. No native total, inode or
physical capacity theorem is created by this successor.
"""

from __future__ import annotations
from pathlib import Path

from . import s12_b2_allocation_limits as old
from . import s12_b2_contract as b
from . import s12_storage as storage

VERSION = "stage12_allocation_limits_b2_ra_g1_v1"
USAGE = "stage12_allocation_usage_b2_ra_g1_v1"
DESCRIPTOR = "stage12_allocation_limits_descriptor_b2_ra_g1_v1"
ROLES = old.ROLES
FIELDS = (old.FIELDS - {"native_bound_evidence_sha256"}) | {
    "native_risk_inventory_sha256",
    "resource_assurance_binding_sha256",
}
POSITIVE = old.POSITIVE


def parse(raw):
    b.require(type(raw) is bytes and len(raw) <= 65536, "B2_RA_LIMIT_SIZE")
    value = storage.metadata(raw)
    b.require(
        set(value) == FIELDS and value["schema_version"] == VERSION,
        "B2_RA_LIMIT_FIELDS",
    )
    for field in POSITIVE:
        b.uint(value[field], True)
    for field in FIELDS - POSITIVE - {"schema_version", "invocations"}:
        b.validate_type(value[field], "D")
    b.require(
        type(value["invocations"]) is dict and set(value["invocations"]) == set(ROLES),
        "B2_RA_LIMIT_FIELDS",
    )
    for amount in value["invocations"].values():
        b.uint(amount)
    b.require(
        value["sqlite_main_bytes"] >= 4096
        and value["sqlite_main_bytes"] <= 256 * 2**20
        and value["duckdb_spill_bytes"] <= 2 * 2**30
        and value["max_raw_pack_bytes"] <= 64 * 2**20
        and value["max_parquet_file_bytes"] <= 64 * 2**20
        and value["max_compressed_frame_bytes"] <= 32 * 2**20
        and value["max_candidate_buffer_bytes"] <= 32 * 2**20
        and value["max_arrow_batch_bytes"] <= 8 * 2**20,
        "B2_RA_LIMIT_VALUE",
    )
    return value


def validate_binding(value, model, command):
    parse(b.canonical(value))
    b.require(
        value["model_sha256"] == b.digest(model)
        and value["command_id"] == command["command_id"]
        and value["native_risk_inventory_sha256"]
        == model["native_risk_inventory_sha256"]
        and value["max_python_write_bytes"] <= command["logical_write_ceiling_bytes"],
        "B2_RA_LIMIT_BINDING",
    )
    components = {x["component_id"]: x for x in model["components"]}
    for role, component, amount in (
        ("SQLITE", "SQLITE_INDEX", "sqlite_main_bytes"),
        ("DUCKDB", "DUCKDB_SPILL", "duckdb_spill_bytes"),
    ):
        b.require(
            value["invocations"][role] <= command["allocations"][component]
            and (
                value["invocations"][role] == 0
                or value[amount] <= components[component]["logical_prewrite_limit"]
            ),
            "B2_RA_LIMIT_BINDING",
        )
    b.require(
        value["invocations"]["DUCKDB"] <= command["allocations"]["DUCKDB_DATABASE"]
        and value["invocations"]["SQLITE"] + value["invocations"]["DUCKDB"]
        <= command["allocations"]["NATIVE_AUXILIARY"],
        "B2_RA_NATIVE_INVOCATIONS",
    )
    b.require(
        2 * value["max_candidate_buffer_bytes"]
        + value["max_arrow_batch_bytes"]
        + value["max_compressed_frame_bytes"]
        <= command["max_memory_bytes"],
        "B2_RA_LIMIT_BINDING",
    )
    files = (
        "PARQUET_FILE",
        "RAW_PACK_FILE",
        "EXCLUSIVE_FILE",
        "EVENT_FILE",
        "PREFIX_FILE",
        "COMPARISON_FILE",
        "ADMIN_FILE",
    )
    b.require(
        sum(value["invocations"][x] for x in files)
        <= command["creation_attempt_ceiling"],
        "B2_RA_LIMIT_BINDING",
    )
    allocations = command["allocations"]
    for role, maximum in (
        ("EVENT_FILE", allocations["EVENTS"]),
        ("CONTROL_BEGIN", allocations["CONTROL_ATTEMPT_METADATA"]),
        ("CONTROL_FINISH", allocations["CONTROL_ATTEMPT_METADATA"]),
        ("CANDIDATE_BUFFER", allocations["CANDIDATE_ORIGINAL"]),
        (
            "COMPRESSED_FRAME",
            allocations["DATA_RAW"]
            + allocations["CONTROL_RAW"]
            + allocations["RAW_PACKS"],
        ),
    ):
        b.require(value["invocations"][role] <= maximum, "B2_RA_LIMIT_BINDING")


class Controls(old.Controls):
    def __init__(self, value, *, check=lambda: None, prewrite=None):
        import threading

        self.value = parse(b.canonical(value))
        self.check = check
        self.prewrite = prewrite
        self.counts = dict.fromkeys(ROLES, 0)
        self.python_bytes = 0
        self.lock = threading.Lock()

    def claim(self, role, size=0):
        b.uint(size)
        if self.prewrite is not None:
            file_roles = {
                "PARQUET_FILE",
                "RAW_PACK_FILE",
                "EXCLUSIVE_FILE",
                "EVENT_FILE",
                "PREFIX_FILE",
                "COMPARISON_FILE",
                "ADMIN_FILE",
            }
            self.prewrite(next_write_bytes=size, next_creations=int(role in file_roles))
        return super().claim(role, size)

    def bytes(self, size):
        b.uint(size)
        if self.prewrite is not None:
            self.prewrite(next_write_bytes=size, next_creations=0)
        return super().bytes(size)

    def usage(self):
        with self.lock:
            return {
                "schema_version": USAGE,
                "selection_sha256": b.digest(self.value),
                "invocations": dict(self.counts),
                "python_reserved_bytes": self.python_bytes,
                "native_maximum": "NOT_PROVEN",
                "physical_maximum": "NOT_PROVEN",
            }

    def reserve_remaining(self, *, report_bytes=65536):
        self.check()
        b.uint(report_bytes, True)
        with self.lock:
            remaining = {
                role: self.value["invocations"][role] - self.counts[role]
                for role in ROLES
            }
            b.require(remaining["EXCLUSIVE_FILE"] >= 3, "B2_RS1_INVOCATION_BUDGET")
            remaining["EXCLUSIVE_FILE"] -= 1
            allowance = (
                self.value["max_python_write_bytes"] - self.python_bytes - report_bytes
            )
            b.require(allowance > 0, "B2_RS1_WRITE_BUDGET")
            for role, count in remaining.items():
                self.counts[role] += count
            self.python_bytes += allowance
        selected = dict(
            self.value, invocations=remaining, max_python_write_bytes=allowance
        )
        return Controls(selected, check=self.check, prewrite=self.prewrite)


def descriptor():
    return {
        "descriptor_version": DESCRIPTOR,
        "record": VERSION,
        "parent_descriptor_sha256": old.DESCRIPTOR_SHA256,
        "normative_schema_sha256": "193c6b749af1981e20b829a6d25d07103966e0bbffeb07c5e38ed895f5a32e25",
        "fields": sorted(FIELDS),
        "positive_integer_fields": sorted(POSITIVE),
        "invocation_roles": list(ROLES),
        "usage": USAGE,
        "native_maximum": "NOT_PROVEN",
        "physical_maximum": "NOT_PROVEN",
        "sinks": "UNCHANGED_EXCLUSIVE_PRECHARGE_POISON_AND_NO_REFUND",
    }


DESCRIPTOR_SHA256 = b.digest(descriptor())
_descriptor_raw = (
    Path(__file__).resolve().parents[4]
    / "docs/scientific_assets"
    / (DESCRIPTOR + ".json")
).read_bytes()
b.require(
    _descriptor_raw == b.canonical(descriptor())
    and b.sha(_descriptor_raw).hex() == DESCRIPTOR_SHA256,
    "B2_RA_DESCRIPTOR_CHANGED",
)

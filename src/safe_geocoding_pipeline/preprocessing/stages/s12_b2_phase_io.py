"""Bounded immutable local phase output and sealed-campaign observation readers."""

from __future__ import annotations
import os
from itertools import zip_longest
from . import s12_b2_contract as b
from . import s12_b2_catalog as catalog_module
from . import s12_b2_calibration as cal
from . import s12_b2_audit as audit
from . import s12_b2_recovery as recovery
from . import s12_b2_evidence as evidence
from . import s12_b2_operations as o
from . import s12_public_journal as journal
from . import s12_storage as io
from . import s11_semantic_contract as s11


class PhaseOutput:
    """Single bounded writer; failed output is preserved and cannot be reused."""

    def __init__(self, root, *, writer_guard_ms, max_bytes, max_rows, secret_guard):
        for x in (writer_guard_ms, max_bytes, max_rows):
            b.uint(x, True)
        self.root, self.maximum, self.rows_max, self.guard = (
            root,
            max_bytes,
            max_rows,
            secret_guard,
        )
        self.writer = journal.Writer(root, 1, writer_guard_ms, lambda: None)
        self.rows = 0
        self.bytes = 0
        self.fd = None
        self.writer.call(self._open)

    def _open(self):
        self.fd = os.open(
            self.root / "comparisons.json",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        self._write(b"[")

    def _write(self, raw):
        self.writer.assert_owner()
        self.guard(raw)
        b.require(self.bytes + len(raw) <= self.maximum, "B2_PHASE_STORAGE_BUDGET")
        view = memoryview(raw)
        while view:
            n = os.write(self.fd, view)
            b.require(n > 0, "B2_PHASE_WRITE_FAILED")
            view = view[n:]
        self.bytes += len(raw)

    def append(self, row):
        raw = b.canonical(row)[:-1]
        b.require(
            len(raw) <= b.MAX_METADATA and self.rows < self.rows_max,
            "B2_PHASE_ROW_BUDGET",
        )
        self.writer.call(lambda: self._write((b"," if self.rows else b"") + raw))
        self.rows += 1

    def finish(self, result, *, inputs):
        b.validate(result, "stage12_calibration_result_b2_v1")

        def finish():
            self._write(b"]\n")
            os.fsync(self.fd)
            os.close(self.fd)
            self.fd = None
            b.require(
                s11.sha256_file(self.root / "comparisons.json")
                == result["comparison_inventory_sha256"],
                "B2_COMPARISON_HASH",
            )
            for name, obj in (("result.json", result), ("inputs.json", inputs)):
                raw = b.canonical(obj)
                self.guard(raw)
                b.require(
                    self.bytes + len(raw) <= self.maximum, "B2_PHASE_STORAGE_BUDGET"
                )
                self.bytes += len(raw)
                io.write(self.root / name, raw)
            manifest = {
                "schema_version": "stage12_calibration_phase_output_b2_v1",
                "scope": result["population_scope"],
                "result_sha256": b.digest(result),
                "inputs_sha256": b.digest(inputs),
                "comparison_sha256": result["comparison_inventory_sha256"],
                "comparison_rows": self.rows,
                "inventory": io.file_inventory(
                    self.root, ("comparisons.json", "result.json", "inputs.json")
                ),
            }
            raw = b.canonical(manifest)
            b.require(
                self.bytes + len(raw) + 1024 <= self.maximum, "B2_PHASE_STORAGE_BUDGET"
            )
            io.write(self.root / "manifest.json", raw)
            return b.digest(manifest)

        h = self.writer.call(finish)
        # Both markers are mandatory; an interrupted release cannot be reopened.
        self.writer.call(lambda: io.write(self.root / "_COMMITTED", b""))
        self.writer.release({"manifest_sha256": h}, segment_seal=False)
        return reopen_phase(self.root, h)

    def abort(self):
        if self.writer.closed:
            return
        self.writer.abort()
        # Never close a descriptor under an uncertain still-running disk write.
        if not self.writer.thread.is_alive() and self.fd is not None:
            os.close(self.fd)
            self.fd = None


def reopen_phase(root, expected_hash):
    raw = io.read(root / "manifest.json")
    b.require(b.sha(raw).hex() == expected_hash, "B2_PHASE_HASH")
    m = io.metadata(raw)
    b.require(
        set(m)
        == {
            "schema_version",
            "scope",
            "result_sha256",
            "inputs_sha256",
            "comparison_sha256",
            "comparison_rows",
            "inventory",
        }
        and m["schema_version"] == "stage12_calibration_phase_output_b2_v1",
        "B2_PHASE_SCHEMA",
    )
    io.verify_inventory(
        root,
        m["inventory"],
        extra={
            "manifest.json",
            "_WRITER_RESERVED",
            "_WRITER_RELEASED.json",
            "_COMMITTED",
        },
    )
    b.require(
        io.read(root / "_COMMITTED", limit=0) == b""
        and io.metadata(io.read(root / "_WRITER_RELEASED.json"))
        == {"manifest_sha256": expected_hash},
        "B2_PHASE_UNSEALED",
    )
    result = b.parse(io.read(root / "result.json"), "stage12_calibration_result_b2_v1")
    b.require(
        b.digest(result) == m["result_sha256"]
        and result["population_scope"] == m["scope"]
        and b.sha(io.read(root / "inputs.json")).hex() == m["inputs_sha256"],
        "B2_PHASE_HASH",
    )
    b.require(
        s11.sha256_file(root / "comparisons.json")
        == m["comparison_sha256"]
        == result["comparison_inventory_sha256"],
        "B2_COMPARISON_HASH",
    )
    b.require(
        sum(1 for _ in journal.read_array(root / "comparisons.json"))
        == m["comparison_rows"],
        "B2_COMPARISON_COUNT",
    )
    return result


class CampaignReader:
    """Exact local terminal receipt joins; no user-supplied observation algorithm."""

    def __init__(
        self, segment, *, catalog, rules, gate, closure_hash, scratch, control_adapters
    ):
        self.segment, self.catalog, self.rules, self.gate = (
            segment,
            catalog,
            rules,
            gate,
        )
        self.control_adapters = control_adapters
        self.closure_hash, self.scratch = closure_hash, scratch
        self.counter = 0
        io.reserve(scratch)
        self.start = b.parse(io.read(segment / "campaign_start.json"), o.START)
        self.plan = b.parse(io.read(segment / "plan.json"), o.PLAN)
        self.profile = b.parse(io.read(segment / "profile.json"), o.PROFILE)
        self.science = b.parse(
            io.read(segment / "scientific_start.json"),
            "stage12_campaign_provenance_b2_v1",
        )
        self.validate()
        self.db = catalog_module.connect(scratch / "index.sqlite")
        self.db.execute(
            "create table selected(q blob primary key,work integer,ordinal integer,receipt text)"
        )
        for work, ledger in zip_longest(
            self.works(), journal.read_array(segment / "work_ledger.json")
        ):
            b.require(
                work is not None
                and ledger is not None
                and work["work_id"] == ledger["work_id"]
                and ledger["state"] == "DURABLE_SUCCESS",
                "B2_WORK_TOTALITY",
            )
            if work["kind"] == "DATA":
                ordinal = ledger["charged_ordinals"][-1]
                unit = self.locate(work["work_id"], ordinal)
                self.db.execute(
                    "insert into selected values(?,?,?,?)",
                    (
                        bytes.fromhex(work["query_semantic_id"]),
                        work["work_id"],
                        ordinal,
                        b.sha(io.read(unit / "receipt.json")).hex(),
                    ),
                )
        self.db.commit()
        self.observation = cal.Observation(
            self.plan["workload_kind"],
            self.plan["result_limit"],
            self.plan["repetition"],
            self.plan["population_scope"],
            self.plan["window_plan_sha256"],
            self.db.execute("select count(*) from selected").fetchone()[0],
            o.manifest_digest(q.hex() for q in self.ids()),
            b.sha(io.read(segment / "snapshot.json")).hex(),
            closure_hash,
            b.digest(self.plan),
            self.read,
            self.ids,
            self.validate,
        )

    def works(self):
        return journal.read_array(self.segment / "work.json")

    def locate(self, work, ordinal):
        node = self.segment
        found = None
        while node is not None:
            unit = node / "attempts" / f"{work:020d}_{ordinal:02d}"
            if unit.exists():
                b.require(found is None, "B2_DUPLICATE_RECEIPT")
                found = unit
            node = journal.predecessor_root(node)
        b.require(found is not None, "B2_RECEIPT_MISSING")
        return found

    def receipt(self, work, event):
        unit = self.locate(work["work_id"], event["attempt"])
        b.require(
            b.sha(io.read(unit / "receipt.json")).hex()
            == event["receipt_inventory_sha256"],
            "B2_RECEIPT_HASH",
        )
        if work["kind"] == "DATA":
            return audit.reopen(unit, **self.rules.kwargs())[0]
        recipe = next(
            x
            for x in self.plan["control_recipes"]
            if x["recipe_id"] == work["recipe_id"]
        )
        return audit.report_control(
            unit, recipe, self.control_adapters[work["recipe_id"]]
        )

    def validate(self):
        self.counter += 1
        self.catalog.verify()
        result = recovery.reopen(
            self.segment,
            self.start,
            self.profile,
            self.plan,
            works=self.works,
            verify_receipt=self.receipt,
            scratch=self.scratch / ("verify_" + str(self.counter) + ".sqlite"),
            authority=self.gate,
        )
        b.require(
            result["snapshot"]["disposition"] == "COMPLETED", "B2_CAMPAIGN_INCOMPLETE"
        )
        node = self.segment
        closures = []
        while node is not None:
            closures.append(
                b.parse(io.read(node / "snapshot.json"), o.SNAPSHOT)[
                    "segment_closure_sha256"
                ]
            )
            node = journal.predecessor_root(node)
        evidence.campaign_closure(
            self.gate.records,
            self.closure_hash,
            plan=self.plan,
            start=self.science,
            segments=list(reversed(closures)),
            authority=self.gate,
            population_scope=self.plan["population_scope"],
        )
        return result

    def ids(self):
        for (q,) in self.db.execute("select q from selected order by q"):
            yield q

    def read(self, q):
        row = self.db.execute(
            "select work,ordinal,receipt from selected where q=?", (q,)
        ).fetchone()
        b.require(row is not None, "B2_CALIBRATION_TOTALITY")
        unit = self.locate(row[0], row[1])
        b.require(
            b.sha(io.read(unit / "receipt.json")).hex() == row[2], "B2_RECEIPT_HASH"
        )
        receipt, projection, raw = audit.reopen(unit, **self.rules.kwargs())
        begin, work, science, admission = audit.context(unit)
        b.require(
            work["query_semantic_id"] == q.hex()
            and science == self.science
            and projection is not None
            and receipt["outcome"] in b.SUCCESS,
            "B2_RECEIPT_BINDING",
        )
        return projection, raw

    def close(self):
        self.db.close()

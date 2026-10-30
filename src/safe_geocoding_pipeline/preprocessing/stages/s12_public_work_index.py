"""Bounded ephemeral public work lookup; exact source bytes remain authority."""

from . import s12_public_operations as o
from . import s12_probe as probe

MAX_INDEXED_WORKS = 256


class WorkIndex:
    """At most 256 row hashes, never a retained request/body or durable cache.

    Construction validates the complete frozen work manifest. Every indexed
    lookup rereads the actual source row and compares its exact canonical hash.
    Callers revalidate the full manifest at stage boundaries. Larger populations
    use the previous streaming lookup, with no partially trusted index. Rebuild
    from original inputs for every invocation/reopen; never serialize this object.
    """

    def __init__(self, factory, reader, plan):
        self.factory, self.reader, self.plan = factory, reader, plan
        self.manifest = plan["work_manifest_sha256"]
        self.hashes = {}

        first = True

        def capture():
            nonlocal first
            collecting, first = first, False
            for row in factory():
                if not collecting:
                    yield self.checked(row)
                    continue
                if self.hashes is not None:
                    if len(self.hashes) == MAX_INDEXED_WORKS:
                        self.hashes = None
                    else:
                        o.require(row["work_id"] not in self.hashes)
                        self.hashes[row["work_id"]] = o.digest(row)
                yield row

        o.verify_work_manifest(capture, plan)

    def verify(self):
        o.require(self.plan["work_manifest_sha256"] == self.manifest)
        o.verify_work_manifest(self.factory, self.plan)

    def checked(self, row):
        if self.hashes is not None:
            o.require(self.hashes.get(row["work_id"]) == o.digest(row))
        return row

    def row(self, work_id):
        o.uint(work_id, True)
        if self.hashes is not None:
            o.require(work_id in self.hashes)
            row = self.reader(work_id)
        else:
            row = next((r for r in self.factory() if r["work_id"] == work_id), None)
        o.require(row is not None and row["work_id"] == work_id)
        return self.checked(row)

    def pairs(self, block_id):
        # Public fixture inventory and size<=40 bound this key space, independent
        # of repetitions/population. Store IDs only; reread each predecessor.
        first = {}
        maximum_cells = 40 * len(probe.fixtures())
        for row in self.factory():
            row = self.checked(row)
            if row["kind"] != "DATA" or row["block_id"] != block_id:
                continue
            key = (row["fixture_id"], row["result_limit"])
            if key not in first:
                o.require(len(first) < maximum_cells)
                first[key] = row["work_id"]
            else:
                yield self.row(first[key]), row
        self.verify()

"""Bounded disk catalog and exact Stage11-to-context map-back for B2."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from collections.abc import Callable

from . import s11_semantic_contract as s11
from . import s11_semantic_io as s11io
from . import s11_semantic_publication as s11pub
from . import s12_b2_contract as b
from . import s12_b2_allocation_limits as limits
from . import s12_storage as io
from . import s12_retrieval_contract as c

ACCEPTED = {
    "manifest_sha256": "9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc",
    "semantic_count": 105805,
    "map_count": 142677,
    "source_count": 35000,
    "semantic_sha256": "01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e",
    "map_sha256": "ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3",
    "dataset_sha256": "e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337",
}


def connect(path: Path):
    limits.sqlite_before(path)
    io.private_directory(path.parent)
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    else:
        s11io.private(path)
    db = sqlite3.connect(path, check_same_thread=False)
    try:
        limits.sqlite_cap(db)
    except BaseException:
        db.close()
        raise
    db.execute("pragma cache_size=-2048")
    db.execute("pragma temp_store=FILE")
    db.execute("pragma mmap_size=0")
    db.execute("pragma foreign_keys=ON")
    db.execute("pragma synchronous=FULL")
    # The optional phase guard also runs during long SQLite joins/sorts. It is
    # absent outside a cooperative runtime phase; no query/result is changed.
    db.set_progress_handler(lambda: (io._checkpoint(), 0)[1], 1000)
    return db


class ChannelRows:
    """Reiterable disk join, never an unbounded alias list in context memory."""

    def __init__(self, db, u):
        self.db, self.u = db, u

    def __iter__(self):
        for (raw,) in self.db.execute(
            "select body from channel where u=? order by ordinal", (self.u,)
        ):
            yield json.loads(raw)


class Catalog:
    def __init__(
        self, path: Path, binding: dict, *, expected_file_sha256: str | None = None
    ):
        b.validate(binding, "stage12_stage11_input_binding_b2_v1")
        if path.exists():
            b.require(
                expected_file_sha256 is not None
                and s11.sha256_file(path) == expected_file_sha256,
                "B2_CATALOG_HASH",
            )
        self.path, self.binding, self.file_sha256 = path, binding, expected_file_sha256
        self.db = connect(path)

    def close(self):
        self.db.close()

    @classmethod
    def build(
        cls,
        path,
        binding,
        *,
        semantics: Callable,
        mapping: Callable,
        hypotheses: Callable,
        contexts: Callable,
        families: Callable,
        authority,
    ):
        """Factories reopen hash-validated accepted relations, never a row sample.

        Contexts are the preflight projection of the exact accepted occurrence
        chain, including contexts with no semantic request. Its origin binding
        is separately required by authority, not inferred from its text.
        """
        b.validate(binding, "stage12_stage11_input_binding_b2_v1")
        authority.require("protected_input", b.digest(binding), binding)
        if binding["population_scope"] == b.DEVELOPMENT:
            from ...execution_policy import require_goethe_nhr_slurm

            require_goethe_nhr_slurm("stage12 accepted Stage11 catalog")
            spill = os.environ.get("SQLITE_TMPDIR")
            b.require(
                spill is not None and Path(spill).is_absolute(),
                "B2_PRIVATE_SPILL_REQUIRED",
            )
            io.private_directory(Path(spill))
            b.require(
                all(binding[k] == v for k, v in ACCEPTED.items()),
                "B2_ACCEPTED_POPULATION_REQUIRED",
            )
        b.require(not path.exists(), "B2_CATALOG_EXISTS")
        self = cls(path, binding)
        db = self.db
        db.executescript("""
        create table semantic(q blob primary key, core blob not null, mode text not null, country text not null) without rowid;
        create table context(u blob primary key, source blob not null, metadata blob not null) without rowid;
        create table channel(u blob not null references context(u),ordinal integer,body blob not null,primary key(u,ordinal)) without rowid;
        create table hypothesis(h blob primary key, q blob not null references semantic(q), u blob not null references context(u)) without rowid;
        create table mapping(h blob primary key references hypothesis(h), q blob not null references semantic(q)) without rowid;
        create table family(u blob not null references context(u), h blob references hypothesis(h), name text not null, primary key(u,name)) without rowid;
        create index mapping_query on mapping(q,h);
        create index hypothesis_context on hypothesis(u,h);
        create table membership(q blob not null references semantic(q), cell blob not null, source blob not null, primary key(q,cell,source)) without rowid;
        create index membership_cell on membership(cell,source);
        create table stratum(q blob primary key references semantic(q), body blob not null, ordering blob not null) without rowid;
        create table occurrence_tuple(q blob not null, body blob not null, primary key(q,body)) without rowid;
        """)
        count = 0

        def semantic_rows():
            nonlocal count
            for row in semantics():
                b.require(
                    set(row) == {"query_semantic_id", "core"}, "B2_CATALOG_SCHEMA"
                )
                raw = s11.core_bytes(row["core"])
                qid = s11.semantic_id(raw)
                b.require(row["query_semantic_id"] == qid, "B2_SEMANTIC_ID")
                db.execute(
                    "insert into semantic values(?,?,?,?)",
                    (
                        qid,
                        raw,
                        row["core"]["search_mode"],
                        row["core"]["boundary_country"],
                    ),
                )
                count += 1
                yield row

        observed = s11.relation_digest(
            "semantic_request", binding["semantic_count"], semantic_rows()
        ).hex()
        b.require(
            observed == binding["semantic_sha256"]
            and count == binding["semantic_count"],
            "B2_CATALOG_HASH",
        )
        for row in contexts():
            # This projection is controlled evidence, not a fifth scientific relation.
            required = {
                "query_context_id",
                "stable_source_row_id_v1",
                "country",
                "script",
                "capability",
                "completeness",
                "representation",
                "channels",
                "origin_sha256",
            }
            b.require(
                set(row) == required
                and type(row["completeness"]) is list
                and len(row["completeness"]) == 4
                and all(type(x) is bool for x in row["completeness"]),
                "B2_CONTEXT_INVALID",
            )
            channels = row["channels"]
            row = {**row, "channels": []}
            b.require(
                len(b.canonical(row)) <= b.MAX_METADATA
                and row["representation"] in ("STANDARD", "NATIVE"),
                "B2_CONTEXT_INVALID",
            )
            for k in ("query_context_id", "stable_source_row_id_v1", "origin_sha256"):
                b.validate_type(row[k], "D")
            authority.require("lineage_context", row["origin_sha256"], row)
            db.execute(
                "insert into context values(?,?,?)",
                (
                    bytes.fromhex(row["query_context_id"]),
                    bytes.fromhex(row["stable_source_row_id_v1"]),
                    b.canonical(row),
                ),
            )
            for ordinal, channel in enumerate(channels):
                b.require(
                    len(b.canonical(channel)) <= b.MAX_METADATA, "B2_CHANNEL_SIZE"
                )
                if channel.get("dependence_class") == "PROVEN_DISJOINT":
                    authority.require(
                        "positive_importer_lineage",
                        channel["origin_record_sha256"],
                        channel,
                    )
                db.execute(
                    "insert into channel values(?,?,?)",
                    (
                        bytes.fromhex(row["query_context_id"]),
                        ordinal,
                        b.canonical(channel),
                    ),
                )
        for row in hypotheses():
            q = s11.semantic_id(
                s11.core_bytes(s11.project(row["intent"], row["selection_status"]))
            )
            db.execute(
                "insert into hypothesis values(?,?,?)",
                (row["hypothesis_id"], q, row["query_context_id"]),
            )
            stored = db.execute(
                "select source,metadata from context where u=?",
                (row["query_context_id"],),
            ).fetchone()
            b.require(
                stored is not None
                and stored[0] == row["stable_source_row_id_v1"]
                and json.loads(stored[1])["representation"]
                == row["stage08_representation"],
                "B2_LINEAGE_MISMATCH",
            )
        for row in families():
            if row["hypothesis_id"] is not None:
                expected = db.execute(
                    "select u from hypothesis where h=?", (row["hypothesis_id"],)
                ).fetchone()
                b.require(
                    expected is not None and expected[0] == row["query_context_id"],
                    "B2_LINEAGE_MISMATCH",
                )
                db.execute(
                    "insert into family values(?,?,?)",
                    (row["query_context_id"], row["hypothesis_id"], row["family"]),
                )

        def maps():
            for row in mapping():
                b.require(
                    set(row) == {"hypothesis_id", "query_semantic_id"}, "B2_MAP_SCHEMA"
                )
                expected = db.execute(
                    "select q from hypothesis where h=?", (row["hypothesis_id"],)
                ).fetchone()
                b.require(
                    expected is not None and expected[0] == row["query_semantic_id"],
                    "B2_MAP_MISMATCH",
                )
                db.execute(
                    "insert into mapping values(?,?)",
                    (row["hypothesis_id"], row["query_semantic_id"]),
                )
                yield row

        b.require(
            s11.relation_digest(
                "hypothesis_request_map", binding["map_count"], maps()
            ).hex()
            == binding["map_sha256"],
            "B2_MAP_HASH",
        )
        b.require(
            db.execute("select count(*) from hypothesis").fetchone()[0]
            == binding["map_count"]
            and db.execute("select count(distinct source) from context").fetchone()[0]
            == binding["source_count"],
            "B2_MAP_TOTALITY",
        )
        b.require(
            db.execute(
                "select count(*) from semantic s where not exists(select 1 from mapping m where m.q=s.q)"
            ).fetchone()[0]
            == 0,
            "B2_MAP_TOTALITY",
        )
        db.commit()
        self.make_memberships()
        self.seal()
        return self

    def seal(self):
        self.db.commit()
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        io.fsync_directory(self.path.parent)
        self.file_sha256 = s11.sha256_file(self.path)

    def verify(self):
        s11io.private(self.path)
        b.require(
            self.file_sha256 is not None
            and s11.sha256_file(self.path) == self.file_sha256,
            "B2_CATALOG_CHANGED",
        )

    def core(self, q):
        row = self.db.execute(
            "select core from semantic where q=?",
            (bytes.fromhex(q) if isinstance(q, str) else q,),
        ).fetchone()
        b.require(row is not None, "B2_UNKNOWN_SEMANTIC")
        return s11.decode_core(row[0])

    def semantics(self):
        for q, raw in self.db.execute("select q,core from semantic order by q"):
            yield {"query_semantic_id": q, "core": s11.decode_core(raw)}

    def contexts(self, q):
        for (raw,) in self.db.execute(
            "select distinct c.metadata from context c join hypothesis h on h.u=c.u join mapping m on m.h=h.h where m.q=? order by c.u",
            (q,),
        ):
            row = json.loads(raw)
            row["channels"] = ChannelRows(
                self.db, bytes.fromhex(row["query_context_id"])
            )
            yield row

    def mapback(self):
        # Left join retains even source contexts that generated no eligible query.
        for u, source, h, q in self.db.execute(
            "select c.u,c.source,m.h,m.q from context c left join hypothesis h on h.u=c.u left join mapping m on m.h=h.h order by c.u,m.h"
        ):
            yield {
                "query_context_id": u.hex(),
                "stable_source_row_id_v1": source.hex(),
                "hypothesis_id": h.hex() if h else None,
                "query_semantic_id": q.hex() if q else None,
            }

    def make_memberships(self):
        for q, mode, country in self.db.execute(
            "select q,mode,country from semantic order by q"
        ):
            for context in self.contexts(q):
                u = bytes.fromhex(context["query_context_id"])
                source = bytes.fromhex(context["stable_source_row_id_v1"])
                families = [
                    row[0]
                    for row in self.db.execute(
                        "select distinct name from family f join mapping m on m.h=f.h where f.u=? and m.q=? order by name",
                        (u, q),
                    )
                ]
                b.require(bool(families), "B2_FAMILY_LINEAGE_MISSING")
                labels = [
                    ("country", country),
                    ("script", context["script"]),
                    ("capability", context["capability"]),
                    ("completeness", context["completeness"]),
                    ("representation", context["representation"]),
                    *(("family", x) for x in families),
                ]
                for channel, value in labels:
                    self.db.execute(
                        "insert or ignore into membership values(?,?,?)",
                        (q, b.canonical([channel, value, mode]), source),
                    )
                for family in families:
                    occurrence = [
                        context["script"],
                        context["capability"],
                        context["completeness"],
                        context["representation"],
                        family,
                    ]
                    self.db.execute(
                        "insert or ignore into occurrence_tuple values(?,?)",
                        (q, b.canonical(occurrence)),
                    )
            # Joint occurrence tuples retain correlations across shared contexts.
            # E-encoded full-byte order is the frozen order, not JSON key order.
            parts = []
            weight = 0
            for (encoded,) in self.db.execute(
                "select body from occurrence_tuple where q=?", (q,)
            ):
                weight += len(encoded)
                b.require(weight <= b.MAX_METADATA, "B2_STRATUM_MEMORY_BOUND")
                parts.append(json.loads(encoded))
            parts.sort(key=c.framed)
            full = [country, mode, parts]
            raw = b.canonical(full)
            order = c.identity(
                "SAFE:stage12-tail-stratum:v1",
                [
                    ("protocol_version", "stage12_calibration_protocol_v1"),
                    ("stratum", full),
                ],
            )
            self.db.execute("insert into stratum values(?,?,?)", (q, raw, order))
        self.db.commit()


def load_stage11(root: Path, binding: dict, authority):
    """Open the real accepted catalog only after exact permission/site gates."""
    b.validate(binding, "stage12_stage11_input_binding_b2_v1")
    b.require(
        binding["population_scope"] == b.DEVELOPMENT, "B2_ACCEPTED_POPULATION_REQUIRED"
    )
    authority.require("protected_input", b.digest(binding), binding)
    from ...execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage12 Stage11 input")
    b.require(
        all(binding[k] == v for k, v in ACCEPTED.items()),
        "B2_ACCEPTED_POPULATION_REQUIRED",
    )
    manifest = s11pub.validate_terminal(root, binding["manifest_sha256"], True)
    b.require(
        manifest["logical_sha256"] == binding["dataset_sha256"], "B2_CATALOG_HASH"
    )
    result = {}
    for relation in manifest["relations"]:
        name = relation["name"]
        paths = tuple(s11io.verify_file(root, x) for x in relation["files"])
        b.require(
            relation["schema_sha256"] == s11.descriptor_sha(name).hex(),
            "B2_CATALOG_SCHEMA",
        )
        result[name] = lambda paths=paths: s11io.parquet_rows(paths)
    b.require(set(result) == set(s11.RELATIONS), "B2_CATALOG_SCHEMA")
    return result


def build_accepted(
    path,
    stage11_root,
    binding,
    *,
    repository,
    lineage,
    authority,
    scratch,
    memory_bytes,
):
    """Accepted Stage11 and Stage10 readers plus the reviewed lineage projection.

    lineage exposes rows(), validate(), and binding_sha256. Its projection is
    evidence from the accepted Stage8/9 occurrence/witness chain, not a choice
    of representative context or a new geocoder/source of reference truth.
    Both full validations are mandatory and bracket the external joins.
    """
    from . import s11_semantic_assets as upstream_assets
    from . import s11_semantic_input as upstream
    from . import s12_b2_publication as publication

    authority.require("protected_input", b.digest(binding), binding)
    from .s12_b2_lineage import LineageProjection

    b.require(
        type(lineage) is LineageProjection
        and lineage.population_scope == b.DEVELOPMENT,
        "B2_CONCRETE_LINEAGE_REQUIRED",
    )
    lineage.assert_accepted_chain()
    relations = load_stage11(stage11_root, binding, authority)
    authority.require("lineage_projection", lineage.binding_sha256, {"input": binding})
    lineage.validate()
    accepted = upstream.load_accepted(repository, upstream_assets.verify(repository))
    b.require(
        lineage.accepted.context_binding == accepted.identity_arguments[0]
        and lineage.accepted.identifier == accepted.identity_arguments[1],
        "B2_ACCEPTED_LINEAGE_CHAIN_MISMATCH",
    )
    b.uint(memory_bytes, True)
    io.reserve(scratch)
    db = limits.duck_connect(
        s11io.connect, scratch, memory=str(memory_bytes) + "B", threads=1
    )
    try:
        accepted.register(db)
        upstream.validate(accepted, db)
        result = Catalog.build(
            path,
            binding,
            semantics=relations["semantic_request"],
            mapping=relations["hypothesis_request_map"],
            hypotheses=lambda: publication.sql_rows(
                db, "select * from h order by hypothesis_id"
            ),
            contexts=lineage.rows,
            families=lambda: publication.sql_rows(
                db, "select * from d order by query_context_id,family"
            ),
            authority=authority,
        )
        b.require(
            result.db.execute("select count(*) from context").fetchone()[0] == 69747,
            "B2_CONTEXT_TOTALITY",
        )
        lineage.validate()
        return result
    finally:
        db.close()

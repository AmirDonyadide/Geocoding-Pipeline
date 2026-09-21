"""Disk-backed exact-context joins and replayable lineage selectors."""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
from functools import cache, partial
from pathlib import Path
from typing import Any, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from . import s06_exact_deduplication as s6
from . import s08_address_evidence as s8
from . import s09_reference_contract as s9
from . import s09_reference_io as upstream_io
from . import s10_query_contract as c
from . import s10_query_evidence as evidence
from . import s10_query_families as families
from . import s10_query_input as inputs
from . import s10_query_io as io
from . import s10_query_operations as ops
from . import s10_reference_store as store


@cache
def reference_schema(name: str) -> Any:
    return s9.relation_schema(name)


@cache
def component_schema() -> Any:
    return s8.parser_component_evidence_schema()


@cache
def occurrence_schema() -> Any:
    return s8.representation_occurrence_schema()


@cache
def source_schema() -> Any:
    return s8.source_candidate_map_schema()


def encoded(values: Sequence[Any]) -> bytes:
    return b"".join(c.framed(values))


def certificate(selector: str, rows: Iterable[Sequence[Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        for chunk in c.framed(row):
            digest.update(chunk)
        count += 1
    return {
        "selector_id": selector,
        "selected_count": count,
        "selected_stream_sha256": digest.digest(),
    }


def sql_rows(
    db: duckdb.DuckDBPyConnection,
    query: str,
    parameters: Sequence[Any] = (),
    *,
    batch_rows: int = 1,
) -> Generator[dict[str, Any], None, None]:
    # A separate cursor keeps a streaming parent query alive during nested
    # exact-key reference access. All tables are private operational workspace.
    cursor = db.cursor()
    try:
        reader = cursor.execute(query, list(parameters)).to_arrow_reader(
            batch_size=batch_rows
        )
        for batch in reader:
            if batch.nbytes <= ops.PAGE_BYTES:
                yield from batch.to_pylist()
            else:
                for ordinal in range(batch.num_rows):
                    yield batch.slice(ordinal, 1).to_pylist()[0]
    finally:
        cursor.close()


def one(
    db: duckdb.DuckDBPyConnection, query: str, parameters: Sequence[Any]
) -> dict[str, Any]:
    stream = sql_rows(db, query, parameters)
    try:
        value = next(stream, None)
        c.require(
            value is not None and next(stream, None) is None,
            "STAGE10_EXACT_KEY_CARDINALITY_INVALID",
        )
        assert value is not None
        return value
    finally:
        stream.close()


class ByteCache:
    """Strict byte and entry ceilings; no eligibility decisions cached across rows."""

    def __init__(self, limit: int = 16 * 1024 * 1024) -> None:
        self.limit = limit
        self.size = 0
        self.items: OrderedDict[bytes, tuple[Any, int]] = OrderedDict()

    def get(self, key: bytes) -> Any:
        found = self.items.get(key)
        if found is None:
            return None
        self.items.move_to_end(key)
        return found[0]

    def put(self, key: bytes, value: Any, size: int) -> None:
        # Account for Python/container overhead as well as serialized content.
        weight = 1024 + size * 8
        if weight > self.limit:
            return
        previous = self.items.pop(key, None)
        if previous is not None:
            self.size -= previous[1]
        while self.items and (
            self.size + weight > self.limit or len(self.items) >= 256
        ):
            _, (_, old) = self.items.popitem(last=False)
            self.size -= old
        self.items[key] = value, weight
        self.size += weight


class ReferenceAccess:
    """Public-object keys and accepted witness sets, with disk-backed dedup."""

    def __init__(
        self,
        db: duckdb.DuckDBPyConnection,
        root: Path | None = None,
        progress: ops.Progress | None = None,
        prepared: store.ReferenceStore | None = None,
    ) -> None:
        self.db = db
        self.root = root
        self.progress = progress or ops.Progress()
        self.cache = ByteCache()
        self.certificates = ByteCache(1024 * 1024)
        self.member_cache = ByteCache(4 * 1024 * 1024)
        self.selection: ops.SelectorAccumulator | None = None
        self.prepared = prepared
        self.prepared_revision: int | None = None

    def _ensure_prepared(self) -> None:
        if self.prepared is not None:
            self.prepared.progress = self.progress
            self.prepared.prepare()
            if self.prepared_revision != self.prepared.revision:
                self.cache = ByteCache()
                self.certificates = ByteCache(1024 * 1024)
                self.member_cache = ByteCache(4 * 1024 * 1024)
                self.prepared_revision = self.prepared.revision

    def _material(
        self, name: str, key: str, identifier: bytes
    ) -> tuple[Mapping[str, Any], bytes]:
        self._ensure_prepared()
        cache_key = name.encode() + identifier
        material = self.cache.get(cache_key)
        if material is None:
            if self.prepared is not None:
                record, payload = self.prepared.lookups[name].get(identifier)
                self.progress.counts["reference_store_lookups"] = (
                    self.progress.counts.get("reference_store_lookups", 0) + 1
                )
            else:
                record = one(
                    self.db, f"SELECT * FROM stage10_{name} WHERE {key}=?", [identifier]
                )
                relation = {
                    "capabilities": "reference_capability",
                    "objects": "reference_object",
                    "registry": "reference_registry",
                }[name]
                payload = encoded(c.ordered_values(record, reference_schema(relation)))
            material = record, payload
            self.cache.put(cache_key, material, len(payload) * 2)
        return material[0], material[1]

    def _record(self, name: str, key: str, identifier: bytes) -> Mapping[str, Any]:
        return dict(self._material(name, key, identifier)[0])

    def capability(self, identifier: bytes) -> Mapping[str, Any]:
        return self._record("capabilities", "capability_id", identifier)

    def object(self, identifier: bytes) -> Mapping[str, Any]:
        return self._record("objects", "reference_object_id", identifier)

    def registry(self, identifier: bytes) -> Mapping[str, Any]:
        return self._record("registry", "reference_version_id", identifier)

    def members(self, identifier: bytes) -> Iterator[Mapping[str, Any]]:
        self._ensure_prepared()
        if self.prepared is not None:
            for row, _ in self.prepared.lookups["members"].members(identifier):
                yield row
            return
        cached = self.member_cache.get(identifier)
        if cached is not None:
            yield from cached
            return
        saved: list[dict[str, Any]] | None = []
        size = 0
        for row in sql_rows(
            self.db,
            "SELECT * FROM stage10_members WHERE match_set_id=? ORDER BY member_ordinal",
            [identifier],
        ):
            if saved is not None:
                size += 1024 + len(
                    encoded(
                        c.ordered_values(
                            row, reference_schema("reference_match_member")
                        )
                    )
                )
                if 1024 + 8 * size > self.member_cache.limit:
                    saved = None
                else:
                    saved.append(row)
            yield row
        if saved is not None:
            self.member_cache.put(identifier, tuple(saved), size)

    def witnesses(self, row: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
        count = row["witness_count"]
        singleton, match = row["single_witness"], row["match_set_id"]
        c.require(
            (count == 0 and singleton is None and match is None)
            or (count == 1 and singleton is not None and match is None)
            or (count > 1 and singleton is None and match is not None),
            "STAGE10_WITNESS_REPRESENTATION_INVALID",
        )
        if count == 1:
            assert singleton is not None
            yield singleton
        elif count > 1:
            seen = 0
            for member in self.members(match):
                c.require(
                    member["member_ordinal"] == seen, "STAGE10_WITNESS_ORDINAL_INVALID"
                )
                yield member["witness"]
                seen += 1
            c.require(seen == count, "STAGE10_WITNESS_COUNT_INVALID")

    def _select(self, section: int, key: bytes, values: Sequence[Any]) -> None:
        assert self.selection is not None
        self.selection.add(section, key, encoded(values))

    def _select_record(
        self, section: int, name: str, key: str, identifier: bytes
    ) -> None:
        assert self.selection is not None
        self.selection.add(
            section, identifier, self._material(name, key, identifier)[1]
        )

    def _select_registry(self, identifier: bytes) -> None:
        self._select_record(4, "registry", "reference_version_id", identifier)

    def _select_object(self, identifier: bytes, version: bytes) -> Mapping[str, Any]:
        first = self.object(identifier)
        current = first
        ancestors = set()
        while True:
            key = current["reference_object_id"]
            c.require(
                key not in ancestors and current["reference_version_id"] == version,
                "STAGE10_REFERENCE_ANCESTRY_INVALID",
            )
            ancestors.add(key)
            self._select_record(2, "objects", "reference_object_id", key)
            self._select_registry(version)
            parent = current["explicit_parent_id"]
            if parent is None:
                return first
            current = self.object(parent)

    def witness_certificate(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        with self.progress.measure("certificate"):
            return self._cached_witness_certificate(rows)

    def _cached_witness_certificate(
        self, rows: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        self._ensure_prepared()
        key = encoded(
            tuple(
                (
                    r["reference_version_id"],
                    r["reference_asset_id"],
                    r["capability_id"],
                    r["rule_capability_id"],
                    r["question_catalog_id"],
                    r["witness_count"],
                    None
                    if r["single_witness"] is None
                    else s9.witness_tuple(r["single_witness"]),
                    r["match_set_id"],
                )
                for r in rows
            )
        )
        cached = self.certificates.get(key)
        if cached is not None:
            return dict(cached)
        self.selection = ops.SelectorAccumulator(self.db, self.root)
        try:
            with self.progress.measure("certificate_build"):
                result = self._witness_certificate(rows)
        finally:
            self.selection.close()
            self.selection = None
        self.certificates.put(key, result, len(key) + 128)
        return result

    def _witness_certificate(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        for row in rows:
            version = row["reference_version_id"]
            if version is not None:
                self._select_registry(version)
            for key in ("capability_id", "rule_capability_id"):
                identifier = row[key]
                if identifier is None:
                    continue
                cap = self.capability(identifier)
                c.require(
                    cap["reference_version_id"] == version
                    and cap["question_catalog_id"] == row["question_catalog_id"],
                    "STAGE10_CAPABILITY_FK_INVALID",
                )
                self._select_record(3, "capabilities", "capability_id", identifier)
            if row["single_witness"] is not None:
                values = s9.witness_tuple(row["single_witness"])
                self._select(0, encoded(values), values)
            if row["match_set_id"] is not None:
                if self.prepared is not None:
                    assert self.selection is not None
                    for member, payload in self.prepared.lookups["members"].members(
                        row["match_set_id"]
                    ):
                        self.selection.add(
                            1,
                            encoded((member["match_set_id"], member["member_ordinal"])),
                            payload,
                        )
                else:
                    for member in self.members(row["match_set_id"]):
                        self._select(
                            1,
                            encoded((member["match_set_id"], member["member_ordinal"])),
                            c.ordered_values(
                                member, reference_schema("reference_match_member")
                            ),
                        )
            for witness in self.witnesses(row):
                obj = self._select_object(witness["reference_object_id"], version)
                c.require(
                    obj["asset_id"] == row["reference_asset_id"],
                    "STAGE10_WITNESS_ASSET_FK_INVALID",
                )
                c.require(
                    0 < len(witness["fields"]) <= 16,
                    "STAGE10_WITNESS_FIELD_CARDINALITY_INVALID",
                )
                for pointer in witness["fields"]:
                    pointed = self._select_object(
                        pointer["reference_object_id"], version
                    )
                    c.require(
                        sum(
                            f["field_name"] == pointer["field_name"]
                            and f["ordinal"] == pointer["ordinal"]
                            for f in pointed["fields"]
                        )
                        == 1,
                        "STAGE10_WITNESS_FIELD_FK_INVALID",
                    )
        assert self.selection is not None
        return dict(self.selection.certificate())


class ContextWorkspace:
    """Bounded-memory external joins; source maps remain upstream authorities."""

    def __init__(
        self, accepted: inputs.AcceptedInputs, root: Path, science: bytes
    ) -> None:
        self.accepted, self.root, self.science = accepted, root, science
        root.mkdir(mode=0o700)
        self.progress = ops.Progress(root / "progress")
        raw = upstream_io.bounded_connection(
            root / "spill", database=root / "context.duckdb", memory="8GB", threads=4
        )
        self.db = cast(
            duckdb.DuckDBPyConnection, ops.TimedConnection(raw, self.progress)
        )
        accepted.register_views(self.db)
        self.reference: ReferenceAccess | None = None
        self.parser_certificates = ByteCache(1024 * 1024)
        self.component_cache = ByteCache(4 * 1024 * 1024)
        self.diagnostic_buffer: list[dict[str, Any]] = []
        self.diagnostic_bytes = 0
        self.context_index_revision: int | None = None
        self.reference_store = store.ReferenceStore(self.db, root, self.progress)

    def close(self) -> None:
        if self.progress.terminated:
            return  # Scheduler termination: do not start database cleanup.
        self.flush_diagnostics()
        self.reference_store.close()
        self.db.close()

    def _assert_zero(self, query: str, code: str) -> None:
        result = self.db.execute(query).fetchone()
        c.require(result is not None and result[0] == 0, code)

    def prepare(self) -> None:
        # Fixed-key indexes avoid per-context scans of global evidence/reference
        # relations. Storage is private and disk-backed, not another public map.
        self.db.execute(
            "CREATE TABLE stage10_candidates AS SELECT * EXCLUDE(stage07_libpostal_components) FROM candidate_evidence ORDER BY stage06_exact_candidate_id"
        )
        self.db.execute(
            "CREATE UNIQUE INDEX candidate_key ON stage10_candidates(stage06_exact_candidate_id)"
        )
        for target, source, key in (
            ("stage10_sources", "source_candidate_map", "stable_source_row_id_v1"),
            ("stage10_lines", "stage06_row_map", "stable_source_row_id_v1"),
            ("stage10_registry", "reference_registry", "reference_version_id"),
            ("stage10_capabilities", "reference_capability", "capability_id"),
            ("stage10_objects", "reference_object", "reference_object_id"),
        ):
            self.db.execute(
                f"CREATE TABLE {target} AS SELECT * FROM {source} ORDER BY {key}"
            )
            self.db.execute(f"CREATE UNIQUE INDEX {target}_key ON {target}({key})")
        self.db.execute(
            "CREATE TABLE stage10_components AS SELECT * FROM parser_component_evidence ORDER BY stage06_exact_candidate_id,stage08_component_ordinal"
        )
        self.db.execute(
            "CREATE INDEX component_candidate ON stage10_components(stage06_exact_candidate_id)"
        )
        self.db.execute(
            "CREATE TABLE stage10_source_reference AS SELECT * FROM candidate_reference_evidence WHERE evidence_scope='SOURCE_ROW' ORDER BY stable_source_row_id_v1,stage06_exact_candidate_id,evidence_id"
        )
        self.db.execute(
            "CREATE INDEX reference_source ON stage10_source_reference(stable_source_row_id_v1)"
        )
        self.db.execute(
            "CREATE TABLE stage10_members AS SELECT * FROM reference_match_member WHERE match_set_id IN (SELECT DISTINCT match_set_id FROM stage10_source_reference WHERE match_set_id IS NOT NULL) ORDER BY match_set_id,member_ordinal"
        )
        self.db.execute("CREATE INDEX member_set ON stage10_members(match_set_id)")
        self._assert_zero(
            "SELECT count(*) FROM stage10_sources s FULL OUTER JOIN stage10_lines l USING(stable_source_row_id_v1) WHERE s.stable_source_row_id_v1 IS NULL OR l.stable_source_row_id_v1 IS NULL OR s.stage06_standard_exact_candidate_id IS DISTINCT FROM l.stage06_standard_exact_candidate_id OR s.stage06_native_exact_candidate_id IS DISTINCT FROM l.stage06_native_exact_candidate_id",
            "STAGE10_SOURCE_MAP_SLOT_MISMATCH",
        )
        self._assert_zero(
            "SELECT count(*) FROM stage10_sources WHERE (stage08_standard_representation_status='PRESENT') IS DISTINCT FROM (stage06_standard_exact_candidate_id IS NOT NULL) OR (stage08_native_representation_status='PRESENT') IS DISTINCT FROM (stage06_native_exact_candidate_id IS NOT NULL)",
            "STAGE10_SOURCE_OCCURRENCE_STATUS_INVALID",
        )
        self._assert_zero(
            "SELECT count(*) FROM (SELECT stage06_exact_candidate_id,count(*) n,min(stage08_component_ordinal) lo,max(stage08_component_ordinal) hi,count(DISTINCT stage08_component_ordinal) un FROM stage10_components GROUP BY 1) p FULL OUTER JOIN stage10_candidates c USING(stage06_exact_candidate_id) WHERE c.stage06_exact_candidate_id IS NULL OR coalesce(p.n,0)<>c.stage08_raw_component_count OR (p.n>0 AND (p.lo<>0 OR p.hi<>p.n-1 OR p.un<>p.n))",
            "STAGE10_COMPONENT_ORDINAL_COUNT_INVALID",
        )
        self._assert_zero(
            "SELECT count(*) FROM stage08_occurrence o LEFT JOIN stage10_candidates c USING(stage06_exact_candidate_id) WHERE c.stage06_exact_candidate_id IS NULL",
            "STAGE10_OCCURRENCE_CANDIDATE_ORPHAN",
        )
        self._assert_zero(
            "SELECT count(*) FROM stage10_candidates c LEFT JOIN (SELECT stage06_exact_candidate_id,count(*) n,count(*) FILTER(WHERE stage08_representation='STANDARD') s,count(*) FILTER(WHERE stage08_representation='NATIVE') v FROM stage08_occurrence GROUP BY 1) o USING(stage06_exact_candidate_id) WHERE c.stage06_occurrence_count IS DISTINCT FROM o.n OR c.stage06_standard_occurrence_count IS DISTINCT FROM o.s OR c.stage06_native_occurrence_count IS DISTINCT FROM o.v",
            "STAGE10_CANDIDATE_OCCURRENCE_COUNT_INVALID",
        )
        self._candidate_certificates()
        # Ordinary scalar Python hashing plus Arrow avoids DuckDB's optional
        # numpy-backed Python-UDF path. This is only a private external-sort cache.
        key_schema = pa.schema(
            [
                pa.field("query_context_id", pa.binary(32), nullable=False),
                *s8.representation_occurrence_schema(),
            ]
        )
        key_writer = io.RelationWriter(self.root / "context_keys", key_schema)
        for occurrence in sql_rows(self.db, "SELECT * FROM stage08_occurrence"):
            key_writer.append(
                {
                    "query_context_id": c.context_id(
                        self.accepted.context_binding,
                        occurrence["stable_source_row_id_v1"],
                        occurrence["stage08_representation"],
                    ),
                    **occurrence,
                }
            )
        key_writer.close()
        self.db.execute(
            "CREATE TABLE stage10_context_keys AS SELECT * FROM "
            + io.parquet_sql(key_writer.paths)
            + " ORDER BY query_context_id"
        )
        self.db.execute(
            "CREATE UNIQUE INDEX context_key ON stage10_context_keys(query_context_id)"
        )
        self._assert_zero(
            "SELECT count(*) FROM (SELECT stable_source_row_id_v1,count(*) n,count(DISTINCT stage08_representation) roles FROM stage10_context_keys GROUP BY 1) WHERE n>2 OR n<>roles",
            "STAGE10_CONTEXT_ROW_BOUND_INVALID",
        )
        self.db.execute(
            "CREATE TABLE stage10_context_diagnostics(query_context_id BLOB, stable_source_row_id_v1 BLOB, stage06_exact_candidate_id BLOB, role VARCHAR, country VARCHAR, boundary_fingerprint BLOB, boundary_value BLOB, country_state VARCHAR, q04_postcode_gate BOOLEAN, q08_postcode_gate BOOLEAN)"
        )
        self.reference_store.prepare()
        self.progress.event("reference_preparation_complete")
        self.reference = ReferenceAccess(
            self.db, self.root, self.progress, self.reference_store
        )
        self.prepare_parser_certificates()
        self.progress.event("parser_preparation_complete")
        self.prepare_context_index()
        self.checkpoint_database()
        self.progress.event("context_index_preparation_complete")

    def prepare_context_index(self) -> None:
        """One external join; private derived index, never a new source map."""
        with self.progress.measure("context_index_preparation"):
            self.db.execute("""CREATE TABLE stage10_generation_contexts AS
SELECT k.query_context_id,k AS occurrence,s AS source,l AS lines,c AS candidate,h.candidate_selector_sha256
FROM stage10_context_keys k JOIN stage10_sources s USING(stable_source_row_id_v1)
JOIN stage10_lines l USING(stable_source_row_id_v1)
JOIN stage10_candidates c ON c.stage06_exact_candidate_id=k.stage06_exact_candidate_id
JOIN stage10_candidate_certificates h ON h.stage06_exact_candidate_id=k.stage06_exact_candidate_id
ORDER BY k.query_context_id""")
            self.db.execute(
                "CREATE UNIQUE INDEX generation_context_key ON stage10_generation_contexts(query_context_id)"
            )
            self._assert_zero(
                """SELECT count(*) FROM stage10_context_keys k
FULL OUTER JOIN stage10_generation_contexts g USING(query_context_id)
WHERE k.query_context_id IS NULL OR g.query_context_id IS NULL""",
                "STAGE10_CONTEXT_INDEX_MAP_BACK_INVALID",
            )
            self.context_index_revision = cast(Any, self.db).source_revision

    def checkpoint_database(self) -> None:
        self.progress.observe_wal(self.root / "context.duckdb")
        with self.progress.measure("database_checkpoint"):
            self.db.execute("CHECKPOINT")
        c.require(
            self.progress.observe_wal(self.root / "context.duckdb") == 0,
            "STAGE10_WAL_CHECKPOINT_INCOMPLETE",
        )

    def flush_diagnostics(self) -> None:
        if not self.diagnostic_buffer:
            return
        schema = (
            self.db.execute("SELECT * FROM stage10_context_diagnostics LIMIT 0")
            .to_arrow_table()
            .schema
        )
        table = pa.Table.from_pylist(self.diagnostic_buffer, schema=schema)
        with self.progress.measure("diagnostic_write"):
            self.db.register("stage10_diagnostic_batch", table)
            try:
                self.db.execute(
                    "INSERT INTO stage10_context_diagnostics SELECT * FROM stage10_diagnostic_batch"
                )
            finally:
                self.db.unregister("stage10_diagnostic_batch")
        self.diagnostic_buffer.clear()
        self.diagnostic_bytes = 0

    def prepare_parser_certificates(self) -> None:
        """One complete component stream; derivative cache, never input authority."""
        schema = pa.schema(
            [
                pa.field("stage06_exact_candidate_id", pa.binary(32), nullable=False),
                pa.field("selected_count", pa.uint64(), nullable=False),
                pa.field("selected_stream_sha256", pa.binary(32), nullable=False),
            ]
        )
        writer = io.RelationWriter(self.root / "parser_certificates", schema)
        previous: bytes | None = None
        count, digest = 0, hashlib.sha256()
        with self.progress.measure("parser_certificate_preparation"):
            for row in sql_rows(
                self.db,
                "SELECT * FROM stage10_components ORDER BY stage06_exact_candidate_id,stage08_component_ordinal",
                # Accepted component values can be giant scalars. Never retain
                # a fixed batch of many such scalars in Arrow/Python memory.
                batch_rows=1,
            ):
                candidate = row["stage06_exact_candidate_id"]
                if previous is not None and candidate != previous:
                    writer.append(
                        {
                            "stage06_exact_candidate_id": previous,
                            "selected_count": count,
                            "selected_stream_sha256": digest.digest(),
                        }
                    )
                    count, digest = 0, hashlib.sha256()
                c.require(
                    row["stage08_component_ordinal"] == count,
                    "STAGE10_COMPONENT_ORDINAL_INVALID",
                )
                for chunk in c.framed(c.ordered_values(row, component_schema())):
                    digest.update(chunk)
                count += 1
                previous = candidate
            if previous is not None:
                writer.append(
                    {
                        "stage06_exact_candidate_id": previous,
                        "selected_count": count,
                        "selected_stream_sha256": digest.digest(),
                    }
                )
            writer.close()
            self.db.execute(
                "CREATE TABLE stage10_parser_certificates AS SELECT c.stage06_exact_candidate_id,coalesce(p.selected_count,0)::UBIGINT selected_count,coalesce(p.selected_stream_sha256,?) selected_stream_sha256 FROM stage10_candidates c LEFT JOIN "
                + io.parquet_sql(writer.paths)
                + " p USING(stage06_exact_candidate_id)",
                [hashlib.sha256().digest()],
            )
            self.db.execute(
                "CREATE UNIQUE INDEX parser_certificate_key ON stage10_parser_certificates(stage06_exact_candidate_id)"
            )
            self._assert_zero(
                "SELECT count(*) FROM stage10_parser_certificates p JOIN stage10_candidates c USING(stage06_exact_candidate_id) WHERE p.selected_count<>c.stage08_raw_component_count",
                "STAGE10_COMPONENT_COUNT_INVALID",
            )

    def _candidate_certificates(self) -> None:
        schema = pa.schema(
            [
                pa.field("stage06_exact_candidate_id", pa.binary(32), nullable=False),
                pa.field("candidate_selector_sha256", pa.binary(32), nullable=False),
            ]
        )
        writer = io.RelationWriter(self.root / "candidate_certificates", schema)
        for path in self.accepted.paths["candidate_evidence"]:
            with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
                for batch in parquet.iter_batches(batch_size=1, use_threads=False):
                    value = batch.column(
                        batch.schema.get_field_index("stage06_candidate_lower")
                    )[0].as_py()
                    identifier = batch.column(
                        batch.schema.get_field_index("stage06_exact_candidate_id")
                    )[0].as_py()
                    c.require(
                        s6.exact_candidate_id_v1(value) == identifier,
                        "STAGE10_EXACT_CANDIDATE_HASH_MISMATCH",
                    )
                    digest = hashlib.sha256()
                    for chunk in io.arrow_row_chunks(batch, 0):
                        digest.update(chunk)
                    writer.append(
                        {
                            "stage06_exact_candidate_id": identifier,
                            "candidate_selector_sha256": digest.digest(),
                        }
                    )
        writer.close()
        self.db.execute(
            "CREATE TABLE stage10_candidate_certificates AS SELECT * FROM "
            + io.parquet_sql(writer.paths)
        )
        self.db.execute(
            "CREATE UNIQUE INDEX certificate_candidate ON stage10_candidate_certificates(stage06_exact_candidate_id)"
        )

    def components(
        self, candidate: bytes, reverse: bool
    ) -> Iterator[Mapping[str, Any]]:
        cached = self.component_cache.get(candidate)
        if cached is not None:
            yield from reversed(cached) if reverse else cached
            return
        saved: list[Mapping[str, Any]] | None = []
        size = 0
        direction = "DESC" if reverse else "ASC"
        for row in sql_rows(
            self.db,
            f"SELECT * FROM stage10_components WHERE stage06_exact_candidate_id=? ORDER BY stage08_component_ordinal {direction}",
            [candidate],
            batch_rows=1,
        ):
            if saved is not None:
                size += 1024 + len(encoded(c.ordered_values(row, component_schema())))
                if 1024 + 8 * size > self.component_cache.limit:
                    saved = None
                else:
                    saved.append(row)
            yield row
        if saved is not None:
            self.component_cache.put(
                candidate, tuple(reversed(saved)) if reverse else tuple(saved), size
            )

    def parser_certificate(self, candidate_id: bytes) -> dict[str, Any]:
        cached = self.parser_certificates.get(candidate_id)
        if cached is not None:
            return dict(cached)
        row = one(
            self.db,
            "SELECT * FROM stage10_parser_certificates WHERE stage06_exact_candidate_id=?",
            [candidate_id],
        )
        result = {
            "selector_id": "PARSER_COMPONENTS_V1",
            "selected_count": row["selected_count"],
            "selected_stream_sha256": row["selected_stream_sha256"],
        }
        self.parser_certificates.put(candidate_id, result, 128)
        return result

    def context_rows(
        self,
        prefix: str | None = None,
        *,
        after: bytes | None = None,
        until: bytes | None = None,
        page_rows: int = ops.PAGE_CONTEXTS,
    ) -> Iterator[dict[str, Any]]:
        c.require(
            prefix is None or re.fullmatch(r"[0-9a-fA-F]{1,2}", prefix) is not None,
            "STAGE10_SHARD_PREFIX_INVALID",
        )
        c.require(1 <= page_rows <= ops.PAGE_CONTEXTS, "STAGE10_PAGE_SIZE_INVALID")
        if self.context_index_revision != cast(Any, self.db).source_revision:
            self.db.execute("DROP TABLE stage10_generation_contexts")
            self.prepare_context_index()
        query = """SELECT * EXCLUDE(query_context_id) FROM stage10_generation_contexts k
WHERE {where} ORDER BY k.query_context_id LIMIT {limit}"""
        while True:
            conditions, parameters = [], []
            if prefix is not None:
                # Exact half-open binary range, instead of hex() on every key.
                lo = bytes.fromhex(prefix.lower().ljust(64, "0"))
                hi_int = int(prefix, 16) + 1
                conditions.append("k.query_context_id>=?")
                parameters.append(lo)
                if hi_int < 16 ** len(prefix):
                    conditions.append("k.query_context_id<?")
                    parameters.append(
                        bytes.fromhex(
                            format(hi_int, "x").zfill(len(prefix)).ljust(64, "0")
                        )
                    )
            if after is not None:
                conditions.append("k.query_context_id>?")
                parameters.append(after)
            if until is not None:
                conditions.append("k.query_context_id<=?")
                parameters.append(until)
            cursor = self.db.cursor()
            rows: list[dict[str, Any]] = []
            size = 0
            try:
                reader = cursor.execute(
                    query.format(
                        where=" AND ".join(conditions) or "TRUE", limit=page_rows
                    ),
                    parameters,
                ).to_arrow_reader(batch_size=1)
                for batch in reader:
                    if rows and size + 8 * batch.nbytes > ops.PAGE_BYTES:
                        break
                    rows.extend(batch.to_pylist())
                    size += 8 * batch.nbytes
            finally:
                cursor.close()
            if not rows:
                return
            last = rows[-1]["occurrence"]["query_context_id"]
            c.require(
                after is None or last > after, "STAGE10_CONTEXT_PAGE_ORDER_INVALID"
            )
            # The cursor is already closed before any context/certificate work.
            yield from rows
            after = last

    def contexts(
        self,
        prefix: str | None = None,
        *,
        diagnostics: bool = True,
        after: bytes | None = None,
        until: bytes | None = None,
        page_rows: int = ops.PAGE_CONTEXTS,
    ) -> Iterator[families.QueryContext]:
        c.require(self.reference is not None, "STAGE10_CONTEXT_WORKSPACE_UNPREPARED")
        try:
            for joined in self.context_rows(
                prefix, after=after, until=until, page_rows=page_rows
            ):
                if diagnostics:
                    self.progress.counts["contexts_loaded"] += 1
                with self.progress.measure("context_construction"):
                    context = self._context(joined, diagnostics)
                yield context
        finally:
            if diagnostics and not self.progress.terminated:
                self.flush_diagnostics()
                self.checkpoint_database()

    def _context(
        self, joined: Mapping[str, Any], diagnostics: bool
    ) -> families.QueryContext:
        assert self.reference is not None
        max_source_checks = sum(len(q.references) for q in s9.QUESTIONS.values())
        occurrence, source, candidate = (
            joined["occurrence"],
            joined["source"],
            joined["candidate"],
        )
        source_id, candidate_id = (
            source["stable_source_row_id_v1"],
            candidate["stage06_exact_candidate_id"],
        )
        role = occurrence["stage08_representation"]
        source_rows: list[dict[str, Any]] = []
        for row in sql_rows(
            self.db,
            "SELECT * FROM stage10_source_reference WHERE stable_source_row_id_v1=? AND stage06_exact_candidate_id=? ORDER BY evidence_id",
            [source_id, candidate_id],
        ):
            c.require(
                len(source_rows) < max_source_checks,
                "STAGE10_SOURCE_EVIDENCE_EXPANSION",
            )
            source_rows.append(row)
        with self.progress.measure("source_field_evidence"):
            policy = evidence.evaluate_source_fields(
                source, candidate, source_rows, self.reference
            )
        line_names = inputs.source_line_fields(role)
        line_values = tuple(joined["lines"][n] for n in line_names)
        c.require(
            line_values[0] == candidate_id
            and line_values[5] == candidate["stage06_candidate_lower"]
            and line_values[6] is True,
            "STAGE10_SOURCE_LINE_CANDIDATE_MISMATCH",
        )
        certs = {
            "CANDIDATE_V1": {
                "selector_id": "CANDIDATE_V1",
                "selected_count": 1,
                "selected_stream_sha256": joined["candidate_selector_sha256"],
            },
            "OCCURRENCE_V1": certificate(
                "OCCURRENCE_V1",
                [c.ordered_values(occurrence, occurrence_schema())],
            ),
            "SOURCE_CONTEXT_V1": certificate(
                "SOURCE_CONTEXT_V1",
                [c.ordered_values(source, source_schema())],
            ),
            "SOURCE_LINES_V1": certificate("SOURCE_LINES_V1", [line_values]),
            "PARSER_COMPONENTS_V1": self.parser_certificate(candidate_id),
            "SOURCE_REFERENCE_V1": certificate(
                "SOURCE_REFERENCE_V1",
                (
                    c.ordered_values(
                        row, reference_schema("candidate_reference_evidence")
                    )
                    for row in source_rows
                ),
            ),
            "REFERENCE_WITNESSES_V1": self.reference.witness_certificate(source_rows),
        }
        context = families.QueryContext(
            self.accepted.context_binding,
            self.accepted.identifier,
            self.science,
            source_id,
            role,
            candidate_id,
            candidate["stage06_candidate_lower"],
            line_values[1:5],
            line_values[8],
            line_values[7],
            candidate["stage07_parse_status"],
            candidate["stage08_raw_component_count"],
            partial(self.components, candidate_id),
            tuple(
                source[n]
                for n in (
                    "stage04_lower_city",
                    "stage04_lower_postcode",
                    "stage04_lower_region_in_country",
                    "stage04_lower_country_iso_code",
                )
            ),
            source["stage03_clean_postcode"],
            source["stage03_clean_city"],
            policy,
            certs,
            self.root,
            self.progress,
        )
        context.validate()
        c.require(
            context.identifier == occurrence["query_context_id"],
            "STAGE10_CONTEXT_KEY_COLLISION",
        )
        if diagnostics:
            raw_country = source["stage03_clean_country_iso_code"]
            state = (
                "SOURCE_CODE_RECOGNIZED"
                if policy.country is not None
                else "SOURCE_CODE_MISSING"
                if not raw_country
                else "SOURCE_CODE_MALFORMED"
                if re.fullmatch(r"[A-Za-z]{2}", raw_country) is None
                else "SOURCE_CODE_UNRECOGNIZED"
            )
            diagnostic = {
                "query_context_id": context.identifier,
                "stable_source_row_id_v1": source_id,
                "stage06_exact_candidate_id": candidate_id,
                "role": role,
                "country": policy.country,
                "boundary_fingerprint": c.identity(
                    "stage10-boundary-context:v1", context.lines
                ),
                "boundary_value": encoded(context.lines),
                "country_state": state,
                "q04_postcode_gate": "Q04" in policy.contradiction_capabilities,
                "q08_postcode_gate": "Q08" in policy.contradiction_capabilities,
            }
            size = 1024 + 8 * len(diagnostic["boundary_value"])
            if self.diagnostic_buffer and self.diagnostic_bytes + size > ops.PAGE_BYTES:
                self.flush_diagnostics()
                self.checkpoint_database()
            self.diagnostic_buffer.append(diagnostic)
            self.diagnostic_bytes += size
            if (
                len(self.diagnostic_buffer) >= ops.PAGE_CONTEXTS
                or self.diagnostic_bytes >= ops.PAGE_BYTES
            ):
                self.flush_diagnostics()
                self.checkpoint_database()
        return context

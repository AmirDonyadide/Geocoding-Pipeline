"""Disk-backed exact-context joins and replayable lineage selectors."""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

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
    db: duckdb.DuckDBPyConnection, query: str, parameters: Sequence[Any] = ()
) -> Generator[dict[str, Any], None, None]:
    # A separate cursor keeps a streaming parent query alive during nested
    # exact-key reference access. All tables are private operational workspace.
    cursor = db.cursor()
    try:
        reader = cursor.execute(query, list(parameters)).to_arrow_reader(batch_size=1)
        for batch in reader:
            yield from batch.to_pylist()
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

    def __init__(self, db: duckdb.DuckDBPyConnection) -> None:
        self.db = db
        self.cache = ByteCache()
        self.certificates = ByteCache(1024 * 1024)
        db.execute(
            "CREATE TABLE selector_selection(section UTINYINT, sort_key BLOB, payload BLOB, PRIMARY KEY(section,sort_key))"
        )

    def _record(self, name: str, key: str, identifier: bytes) -> Mapping[str, Any]:
        cache_key = name.encode() + identifier
        record = self.cache.get(cache_key)
        if record is None:
            record = one(
                self.db, f"SELECT * FROM stage10_{name} WHERE {key}=?", [identifier]
            )
            relation = {
                "capabilities": "reference_capability",
                "objects": "reference_object",
                "registry": "reference_registry",
            }[name]
            size = len(encoded(c.ordered_values(record, s9.relation_schema(relation))))
            self.cache.put(cache_key, record, size)
        return dict(record)

    def capability(self, identifier: bytes) -> Mapping[str, Any]:
        return self._record("capabilities", "capability_id", identifier)

    def object(self, identifier: bytes) -> Mapping[str, Any]:
        return self._record("objects", "reference_object_id", identifier)

    def registry(self, identifier: bytes) -> Mapping[str, Any]:
        return self._record("registry", "reference_version_id", identifier)

    def members(self, identifier: bytes) -> Iterator[dict[str, Any]]:
        yield from sql_rows(
            self.db,
            "SELECT * FROM stage10_members WHERE match_set_id=? ORDER BY member_ordinal",
            [identifier],
        )

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
        payload = encoded(values)
        # Conflict checks complete encoded rows. No arbitrary truncation or
        # growing Python object-ID set; SQLite-like ownership lives in DuckDB.
        stored = self.db.execute(
            "INSERT INTO selector_selection VALUES (?,?,?) ON CONFLICT(section,sort_key) DO UPDATE SET payload=selector_selection.payload RETURNING payload",
            [section, key, payload],
        ).fetchone()
        c.require(
            stored is not None and stored[0] == payload, "STAGE10_SELECTOR_ID_COLLISION"
        )

    def _select_registry(self, identifier: bytes) -> None:
        record = self.registry(identifier)
        self._select(
            4,
            identifier,
            c.ordered_values(record, s9.relation_schema("reference_registry")),
        )

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
            self._select(
                2,
                key,
                c.ordered_values(current, s9.relation_schema("reference_object")),
            )
            self._select_registry(version)
            parent = current["explicit_parent_id"]
            if parent is None:
                return first
            current = self.object(parent)

    def witness_certificate(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
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
        self.db.execute("BEGIN TRANSACTION")
        try:
            result = self._witness_certificate(rows)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.certificates.put(key, result, len(key) + 128)
        return result

    def _witness_certificate(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        self.db.execute("DELETE FROM selector_selection")
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
                self._select(
                    3,
                    identifier,
                    c.ordered_values(cap, s9.relation_schema("reference_capability")),
                )
            if row["single_witness"] is not None:
                values = s9.witness_tuple(row["single_witness"])
                self._select(0, encoded(values), values)
            if row["match_set_id"] is not None:
                for member in self.members(row["match_set_id"]):
                    self._select(
                        1,
                        encoded((member["match_set_id"], member["member_ordinal"])),
                        c.ordered_values(
                            member, s9.relation_schema("reference_match_member")
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
        digest = hashlib.sha256()
        count = 0
        for row in upstream_io.sorted_rows(
            self.db,
            "SELECT section,payload FROM selector_selection ORDER BY section,sort_key",
            batch_rows=1,
        ):
            for chunk in c.framed((row["section"],)):
                digest.update(chunk)
            digest.update(row["payload"])
            count += 1
        return {
            "selector_id": "REFERENCE_WITNESSES_V1",
            "selected_count": count,
            "selected_stream_sha256": digest.digest(),
        }


class ContextWorkspace:
    """Bounded-memory external joins; source maps remain upstream authorities."""

    def __init__(
        self, accepted: inputs.AcceptedInputs, root: Path, science: bytes
    ) -> None:
        self.accepted, self.root, self.science = accepted, root, science
        root.mkdir(mode=0o700)
        self.db = upstream_io.bounded_connection(
            root / "spill", database=root / "context.duckdb", memory="8GB", threads=4
        )
        accepted.register_views(self.db)
        self.reference: ReferenceAccess | None = None
        self.parser_certificates = ByteCache(1024 * 1024)

    def close(self) -> None:
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
        self.reference = ReferenceAccess(self.db)

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
        direction = "DESC" if reverse else "ASC"
        yield from sql_rows(
            self.db,
            f"SELECT * FROM stage10_components WHERE stage06_exact_candidate_id=? ORDER BY stage08_component_ordinal {direction}",
            [candidate],
        )

    def parser_certificate(self, candidate_id: bytes) -> dict[str, Any]:
        cached = self.parser_certificates.get(candidate_id)
        if cached is not None:
            return dict(cached)
        result = certificate(
            "PARSER_COMPONENTS_V1",
            (
                c.ordered_values(row, s8.parser_component_evidence_schema())
                for row in self.components(candidate_id, False)
            ),
        )
        self.parser_certificates.put(candidate_id, result, 128)
        return result

    def contexts(
        self, prefix: str | None = None, *, diagnostics: bool = True
    ) -> Iterator[families.QueryContext]:
        c.require(self.reference is not None, "STAGE10_CONTEXT_WORKSPACE_UNPREPARED")
        assert self.reference is not None
        query = """SELECT k AS occurrence,s AS source,l AS lines,c AS candidate,h.candidate_selector_sha256
FROM stage10_context_keys k JOIN stage10_sources s USING(stable_source_row_id_v1)
JOIN stage10_lines l USING(stable_source_row_id_v1)
JOIN stage10_candidates c ON c.stage06_exact_candidate_id=k.stage06_exact_candidate_id
JOIN stage10_candidate_certificates h ON h.stage06_exact_candidate_id=k.stage06_exact_candidate_id
{where}
ORDER BY k.query_context_id""".format(
            where=""
            if prefix is None
            else "WHERE starts_with(hex(k.query_context_id), "
            + io.sql_literal(prefix.upper())
            + ")"
        )
        c.require(
            prefix is None or re.fullmatch(r"[0-9a-fA-F]{1,2}", prefix) is not None,
            "STAGE10_SHARD_PREFIX_INVALID",
        )
        max_source_checks = sum(len(q.references) for q in s9.QUESTIONS.values())
        for joined in sql_rows(self.db, query):
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
                    [
                        c.ordered_values(
                            occurrence, s8.representation_occurrence_schema()
                        )
                    ],
                ),
                "SOURCE_CONTEXT_V1": certificate(
                    "SOURCE_CONTEXT_V1",
                    [c.ordered_values(source, s8.source_candidate_map_schema())],
                ),
                "SOURCE_LINES_V1": certificate("SOURCE_LINES_V1", [line_values]),
                "PARSER_COMPONENTS_V1": self.parser_certificate(candidate_id),
                "SOURCE_REFERENCE_V1": certificate(
                    "SOURCE_REFERENCE_V1",
                    (
                        c.ordered_values(
                            row, s9.relation_schema("candidate_reference_evidence")
                        )
                        for row in source_rows
                    ),
                ),
                "REFERENCE_WITNESSES_V1": self.reference.witness_certificate(
                    source_rows
                ),
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
                self.db.execute(
                    "INSERT INTO stage10_context_diagnostics VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [
                        context.identifier,
                        source_id,
                        candidate_id,
                        role,
                        policy.country,
                        c.identity("stage10-boundary-context:v1", context.lines),
                        encoded(context.lines),
                        state,
                        "Q04" in policy.contradiction_capabilities,
                        "Q08" in policy.contradiction_capabilities,
                    ],
                )
            yield context

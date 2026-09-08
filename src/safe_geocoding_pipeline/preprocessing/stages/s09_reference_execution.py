"""Deterministic shard work and hash-bound restart checkpoints (no CLI bypass)."""

from __future__ import annotations

import os
import shutil
from collections import OrderedDict
from collections.abc import Iterator, Mapping, Sequence
from itertools import groupby
from pathlib import Path
from typing import Any

import duckdb

from . import s09_reference_contract as c
from . import s09_reference_evaluator as e
from . import s09_reference_io as io
from . import s09_reference_postal as postal
from . import s09_reference_questions as q


SHARD_GROUPS = 16
GROUP_WIDTH = 4096 // SHARD_GROUPS
CANDIDATE_COLUMNS = (
    "stage06_exact_candidate_id",
    q.TRUSTED_FIELD,
    "stage07_country_provenance_status",
    "stage08_raw_component_count",
)


def shard_predicate(group: int, column: str) -> str:
    c.require(0 <= group < SHARD_GROUPS, "SHARD_GROUP_INVALID")
    lower = (group * (2**256 // SHARD_GROUPS)).to_bytes(32, "big").hex()
    predicate = f"{column}>=from_hex('{lower}')"
    if group + 1 < SHARD_GROUPS:
        upper = ((group + 1) * (2**256 // SHARD_GROUPS)).to_bytes(32, "big").hex()
        predicate += f" AND {column}<from_hex('{upper}')"
    return predicate


def scheduled_questions(
    db: duckdb.DuckDBPyConnection, group: int
) -> Iterator[q.EvaluationQuestion]:
    source_columns = (
        "stable_source_row_id_v1",
        "stage06_standard_exact_candidate_id",
        "stage06_native_exact_candidate_id",
        *c.SOURCE_FIELDS.values(),
    )
    selected = (
        ",".join("s." + name for name in source_columns)
        + ","
        + ",".join("c." + name for name in CANDIDATE_COLUMNS)
    )
    sql = f"WITH pairs AS (SELECT DISTINCT stable_source_row_id_v1,stage06_exact_candidate_id FROM stage08_occurrence WHERE {shard_predicate(group, 'stage06_exact_candidate_id')}) SELECT {selected} FROM pairs p JOIN source_candidate_map s USING(stable_source_row_id_v1) JOIN candidate_evidence c ON p.stage06_exact_candidate_id=c.stage06_exact_candidate_id ORDER BY c.stage06_exact_candidate_id,s.stable_source_row_id_v1"
    for source in io.sorted_rows(db, sql, batch_rows=1):
        yield from q.source_questions(source, source)
    # Independent cursors keep both streams alive; no candidate text or nested
    # parser list is selected from Stage 8. Component batches are kept small
    # to admit the accepted giant scalar without population-sized buffering.
    with db.cursor() as candidate_cursor, db.cursor() as component_cursor:
        candidate_sql = f"SELECT {','.join(CANDIDATE_COLUMNS)} FROM candidate_evidence WHERE {shard_predicate(group, 'stage06_exact_candidate_id')} ORDER BY stage06_exact_candidate_id"
        component_sql = (
            "SELECT stage06_exact_candidate_id,stage08_component_ordinal,stage08_safe_parser_evidence_component,stage08_raw_libpostal_value FROM parser_component_evidence WHERE "
            + shard_predicate(group, "stage06_exact_candidate_id")
            + " ORDER BY stage06_exact_candidate_id,stage08_component_ordinal"
        )
        component_groups = iter(
            groupby(
                io.sorted_rows(component_cursor, component_sql, batch_rows=16),
                key=lambda row: row["stage06_exact_candidate_id"],
            )
        )
        current = next(component_groups, None)
        for candidate in io.sorted_rows(
            candidate_cursor, candidate_sql, batch_rows=1024
        ):
            key = candidate["stage06_exact_candidate_id"]
            c.require(
                current is None or current[0] >= key, "DANGLING_COMPONENT_CANDIDATE"
            )
            if current is not None and current[0] == key:
                yield from q.parser_questions(candidate, current[1])
                current = next(component_groups, None)
            else:
                yield from q.parser_questions(candidate, ())
        c.require(current is None, "DANGLING_COMPONENT_CANDIDATE")


def checkpoint_binding(
    *, profile: bytes, input_binding: bytes, pack: bytes, executable: str, group: int
) -> dict[str, Any]:
    return {
        "profile_sha256": profile.hex(),
        "input_binding_sha256": input_binding.hex(),
        "public_pack_sha256": pack.hex(),
        "execution_git_sha": executable,
        "logical_shard_first": group * GROUP_WIDTH,
        "logical_shard_last_exclusive": (group + 1) * GROUP_WIDTH,
        "input_range_sha256": c.identity(
            "INPUT_RANGE",
            (input_binding, group * GROUP_WIDTH, (group + 1) * GROUP_WIDTH),
        ).hex(),
        "schema_bundle_sha256": c.schema_bundle_fingerprint().hex(),
    }


def validate_checkpoint(root: Path, binding: Mapping[str, Any]) -> dict[str, Any]:
    c.require(not root.is_symlink() and root.is_dir(), "CHECKPOINT_ROOT_INVALID")
    record = c.read_json(root / "checkpoint.json")
    marker = c.read_json(root / "_COMPLETE.json")
    c.require(
        marker == {"checkpoint_sha256": c.sha256_file(root / "checkpoint.json")}
        and record["binding"] == binding
        and record["state"] == "COMPLETE",
        "CHECKPOINT_BINDING_OR_STATE_INVALID",
    )
    for relation in record["relations"]:
        io.validate_relation(root, relation)
    # Scratch files are retained to diagnose failed attempts. Only canonical,
    # completed, hash-verified relation files are eligible for adoption.
    return record


def adopt_checkpoint(
    source: Path, destination: Path, binding: Mapping[str, Any]
) -> dict[str, Any]:
    record = validate_checkpoint(source, binding)
    c.require(not os.path.lexists(destination), "CHECKPOINT_DESTINATION_EXISTS")
    destination.mkdir(mode=0o700)
    for relation in record["relations"]:
        for item in relation["files"]:
            target = destination / item["relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Copy, never hardlink or alter the failed attempt's files.
            shutil.copyfile(source / item["relative_path"], target)
            target.chmod(0o600)
    adopted = {
        **record,
        "adopted_from_checkpoint_sha256": c.sha256_file(source / "checkpoint.json"),
        "original_job_id": record["job_id"],
        "job_id": os.environ.get("SLURM_JOB_ID", "SYNTHETIC"),
    }
    io.write_json(destination / "checkpoint.json", adopted)
    io.fsync_tree(destination)
    io.write_json(
        destination / "_COMPLETE.json",
        {"checkpoint_sha256": c.sha256_file(destination / "checkpoint.json")},
    )
    io.fsync_directory(destination)
    return validate_checkpoint(destination, binding)


def materialize_group(
    db: duckdb.DuckDBPyConnection,
    view: e.SmallReferenceView,
    index_paths: Sequence[Path],
    root: Path,
    *,
    group: int,
    profile: bytes,
    stage08_logical: bytes,
    binding: Mapping[str, Any],
    memory: str = "8GB",
    threads: int = 4,
) -> dict[str, Any]:
    root.mkdir(mode=0o700)
    io.write_exclusive(root / "_IN_PROGRESS", b"in_progress\n")
    small_writer = io.RelationWriter(
        root / "small_evidence", c.relation_schema("candidate_reference_evidence")
    )
    small_members = io.RelationWriter(
        root / "small_members", c.relation_schema("reference_match_member")
    )
    requests = io.RelationWriter(
        root / "postal_requests", postal.REQUEST_SCHEMA, batch_rows=1024
    )
    cache: OrderedDict[tuple[Any, ...], e.LookupResult] = OrderedDict()
    scheduled = 0
    cache_hits = 0
    questions = 0
    for question in scheduled_questions(db, group):
        questions += 1
        for reference in c.QUESTIONS[question.question_id].references:
            prepared = view.prepare(question, reference)
            scheduled += 1
            if reference == c.GN and prepared.unavailable_reason is None:
                requests.append(
                    postal.postal_request(
                        prepared, profile=profile, stage08_logical=stage08_logical
                    )
                )
                continue
            if prepared.unavailable_reason:
                result = e.LookupResult("NOT_EVALUABLE", prepared.unavailable_reason)
            else:
                key = (
                    reference,
                    question.country,
                    question.question_id,
                    prepared.keys,
                    tuple(a["normalization_id"] for a in prepared.arguments),
                )
                cached_result = cache.get(key)
                if cached_result is None:
                    result = view.lookup_small(prepared)
                    # A bounded optional cache. Excluding giant values from a
                    # cache never excludes them from exact evaluation/output.
                    if (
                        sum(len(k.encode()) for k in prepared.keys if k is not None)
                        <= 4096
                        and len(result.witnesses) <= 16
                    ):
                        cache[key] = result
                        if len(cache) > 4096:
                            cache.popitem(last=False)
                else:
                    result = cached_result
                    cache_hits += 1
                    cache.move_to_end(key)
            row, members = e.finalize_small(
                prepared, result, profile=profile, stage08_logical=stage08_logical
            )
            small_writer.append(row)
            for member in members:
                small_members.append(member)
    small_writer.close()
    small_members.close()
    requests.close()
    postal_evidence, postal_members, postal_metrics = postal.resolve_postal_requests(
        requests.paths,
        index_paths,
        root / "postal_work",
        view.capabilities,
        memory=memory,
        threads=threads,
    )
    with io.bounded_connection(
        root / "canonical_spill", memory=memory, threads=threads
    ) as merge:
        evidence = io.canonicalize(
            merge,
            "candidate_reference_evidence",
            small_writer.paths + postal_evidence,
            root / "candidate_reference_evidence",
        )
        members_record = io.canonicalize(
            merge,
            "reference_match_member",
            small_members.paths + postal_members,
            root / "reference_match_member",
            collapse_exact_duplicates=True,
        )
    c.require(evidence["row_count"] == scheduled, "SHARD_EVALUATION_TOTALITY_MISMATCH")
    record = {
        "binding": dict(binding),
        "state": "COMPLETE",
        "job_id": os.environ.get("SLURM_JOB_ID", "SYNTHETIC"),
        "attempt_id": root.parent.name,
        "relations": [evidence, members_record],
        "metrics": {
            "questions": questions,
            "scheduled_evaluations": scheduled,
            "small_cache_hits": cache_hits,
            **postal_metrics,
        },
    }
    io.write_json(root / "checkpoint.json", record)
    io.fsync_tree(root)
    io.write_json(
        root / "_COMPLETE.json",
        {"checkpoint_sha256": c.sha256_file(root / "checkpoint.json")},
    )
    (root / "_IN_PROGRESS").unlink()
    io.fsync_directory(root)
    return validate_checkpoint(root, binding)

"""Independent bounded units inside the unchanged scientific context order."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from . import s09_reference_io as base
from . import s09_reference_pack as pack
from . import s10_query_contract as c
from . import s10_query_families as families
from . import s10_query_io as io
from . import s10_query_operations as ops
from . import s10_query_publication as publication


def key_window(work: Any, prefix: str, after: bytes | None, count: int) -> list[bytes]:
    c.require(1 <= count <= ops.PAGE_CONTEXTS, "STAGE10_CHECKPOINT_SIZE_INVALID")
    c.require(
        prefix in "0123456789abcdef" and len(prefix) == 1,
        "STAGE10_SHARD_PREFIX_INVALID",
    )
    query = (
        "SELECT query_context_id FROM stage10_context_keys WHERE query_context_id>=?"
    )
    args = [bytes.fromhex(prefix.ljust(64, "0"))]
    if prefix != "f":
        query += " AND query_context_id<?"
        args.append(bytes.fromhex(format(int(prefix, 16) + 1, "x").ljust(64, "0")))
    if after is not None:
        query += " AND query_context_id>?"
        args.append(after)
    return [
        r[0]
        for r in work.db.execute(
            query + " ORDER BY query_context_id LIMIT " + str(count), args
        ).fetchall()
    ]


def validate_unit(
    root: Path,
    binding: Mapping[str, Any],
    prefix: str,
    expected_keys: Sequence[bytes] | None = None,
) -> dict[str, Any]:
    pack.regular_private(root, directory=True)
    raw = publication.read_private(root / "checkpoint.json")
    record = c.read_json(root / "checkpoint.json")
    c.require(
        raw == c.canonical(record)
        and set(record) == {"binding", "prefix", "context_ids", "relations"}
        and record["binding"] == binding
        and record["prefix"] == prefix,
        "STAGE10_CHECKPOINT_BINDING_INVALID",
    )
    try:
        keys = [bytes.fromhex(v) for v in record["context_ids"]]
    except (TypeError, ValueError):
        raise c.Stage10Error("STAGE10_CHECKPOINT_CONTEXT_KEYS_INVALID") from None
    c.require(
        len(keys) <= ops.PAGE_CONTEXTS
        and keys == sorted(set(keys))
        and all(len(k) == 32 and k.hex().startswith(prefix) for k in keys)
        and (expected_keys is None or keys == list(expected_keys)),
        "STAGE10_CHECKPOINT_CONTEXT_KEYS_INVALID",
    )
    c.require(
        [r["name"] for r in record["relations"]] == list(c.RELATIONS),
        "STAGE10_CHECKPOINT_RELATIONS_INVALID",
    )
    readers = {}
    files = ["checkpoint.json"]
    for relation in record["relations"]:
        name = relation["name"]
        paths = io.validate_relation(root, relation)
        readers[name] = iter(base.parquet_rows(paths, batch_rows=1))
        files.extend(f["relative_path"] for f in relation["files"])
    heads = {name: next(reader, None) for name, reader in readers.items()}
    try:
        for key in keys:
            hs: dict[bytes, Mapping[str, Any]] = {}
            ds: dict[str, Mapping[str, Any]] = {}
            for name, reader in readers.items():
                while True:
                    row = heads[name]
                    if row is None or row["query_context_id"] != key:
                        break
                    io.check_identity(
                        row,
                        name,
                        bytes.fromhex(binding["context_binding_sha256"]),
                        bytes.fromhex(binding["input_binding_sha256"]),
                        bytes.fromhex(binding["science_sha256"]),
                    )
                    if name == "query_hypothesis":
                        hs[row["hypothesis_id"]] = row
                    else:
                        ds[row["family"]] = row
                    heads[name] = next(reader, None)
            c.require(
                set(ds) == set(c.FAMILIES), "STAGE10_CHECKPOINT_CONTEXT_COUNT_INVALID"
            )
            fields = (
                "stable_source_row_id_v1",
                "stage08_representation",
                "stage06_exact_candidate_id",
            )
            occurrence = tuple(ds["Q1"][k] for k in fields)
            first: dict[bytes, int] = dict.fromkeys(hs, 0)
            for member in [*hs.values(), *ds.values()]:
                c.require(
                    tuple(member[k] for k in fields) == occurrence,
                    "STAGE10_CHECKPOINT_MAP_BACK_INVALID",
                )
            for decision in ds.values():
                h = decision["hypothesis_id"]
                c.require(h is None or h in hs, "STAGE10_CHECKPOINT_ORPHAN_MEMBERSHIP")
                if decision["membership_state"] == "FIRST_MEMBER":
                    first[h] += 1
            c.require(
                all(v == 1 for v in first.values())
                and len(hs) <= c.ROLE_CEILINGS[occurrence[1]],
                "STAGE10_CHECKPOINT_HYPOTHESIS_CARDINALITY",
            )
        c.require(
            all(v is None for v in heads.values()),
            "STAGE10_CHECKPOINT_INTERVAL_INVALID",
        )
    finally:
        for reader in readers.values():
            close = getattr(reader, "close", None)
            if close is not None:
                close()
    base.topology(root, files)
    return record


def index_rows(root: Path) -> Iterator[dict[str, Any]]:
    pack.regular_private(root / "units.jsonl")
    with (root / "units.jsonl").open("rb") as stream:
        for ordinal, raw in enumerate(stream):
            try:
                item = json.loads(raw)
            except (ValueError, UnicodeError):
                raise c.Stage10Error("STAGE10_CHECKPOINT_INDEX_INVALID") from None
            c.require(
                raw == c.canonical(item)
                and set(item) == {"ordinal", "checkpoint_sha256"}
                and item["ordinal"] == ordinal,
                "STAGE10_CHECKPOINT_INDEX_INVALID",
            )
            yield item


def validate_prefix(
    root: Path, binding: Mapping[str, Any], prefix: str
) -> dict[str, Any]:
    from . import s10_query_materializer as m

    raw = publication.read_private(root / "checkpoint.json")
    record = c.read_json(root / "checkpoint.json")
    c.require(
        raw == c.canonical(record)
        and set(record)
        == {
            "binding",
            "prefix",
            "context_count",
            "unit_count",
            "units_index",
            "relations",
        }
        and record["binding"] == binding
        and record["prefix"] == prefix,
        "STAGE10_CHECKPOINT_BINDING_INVALID",
    )
    c.require(
        record["units_index"] == m.file_record(root / "units.jsonl", root),
        "STAGE10_CHECKPOINT_INDEX_HASH_INVALID",
    )
    previous = None
    count = units = 0
    for item in index_rows(root):
        unit = root / "units" / f"{item['ordinal']:06}"
        c.require(
            c.sha256_file(unit / "checkpoint.json") == item["checkpoint_sha256"],
            "STAGE10_CHECKPOINT_INDEX_HASH_INVALID",
        )
        saved = validate_unit(unit, binding, prefix)
        keys = saved["context_ids"]
        c.require(
            not keys or previous is None or previous < keys[0],
            "STAGE10_CHECKPOINT_UNIT_ORDER_INVALID",
        )
        previous = keys[-1] if keys else previous
        count += len(keys)
        units += 1
    c.require(
        count == record["context_count"] and units == record["unit_count"],
        "STAGE10_CHECKPOINT_CONTEXT_COUNT_INVALID",
    )
    c.require(
        [r["name"] for r in record["relations"]] == list(c.RELATIONS),
        "STAGE10_CHECKPOINT_RELATIONS_INVALID",
    )
    # Compare coalesced output with every immutable unit as complete streams.
    for relation in record["relations"]:
        name = relation["name"]
        paths = io.validate_relation(root, relation)
        observed = iter(base.parquet_rows(paths, batch_rows=1))
        for item in index_rows(root):
            unit = root / "units" / f"{item['ordinal']:06}"
            saved = c.read_json(unit / "checkpoint.json")
            part = next(r for r in saved["relations"] if r["name"] == name)
            for expected in base.parquet_rows(
                [unit / f["relative_path"] for f in part["files"]], batch_rows=1
            ):
                c.require(
                    next(observed, None) == expected,
                    "STAGE10_CHECKPOINT_COALESCE_MISMATCH",
                )
        c.require(next(observed, None) is None, "STAGE10_CHECKPOINT_COALESCE_MISMATCH")
    # Hierarchical topology avoids an in-memory population-wide file inventory.
    pack.regular_private(root, directory=True)
    c.require(
        {p.name for p in root.iterdir()}
        == {"checkpoint.json", "units.jsonl", "units", "relations"},
        "STAGE10_CHECKPOINT_TOPOLOGY_INVALID",
    )
    for folder in ("units", "relations"):
        pack.regular_private(root / folder, directory=True)
    found = 0
    for entry in os.scandir(root / "units"):
        c.require(
            entry.is_dir(follow_symlinks=False)
            and entry.name.isdecimal()
            and entry.name == f"{int(entry.name):06}"
            and int(entry.name) < units,
            "STAGE10_CHECKPOINT_TOPOLOGY_INVALID",
        )
        found += 1
    c.require(found == units, "STAGE10_CHECKPOINT_TOPOLOGY_INVALID")
    base.topology(
        root / "relations",
        [
            str(Path(f["relative_path"]).relative_to("relations"))
            for r in record["relations"]
            for f in r["files"]
        ],
    )
    return record


def generate_prefix(
    work: Any,
    runtime: families.TransformRuntime,
    executable: str,
    prefix: str,
    *,
    resume: Path | None = None,
    unit_contexts: int = ops.PAGE_CONTEXTS,
    output_parent: Path | None = None,
) -> dict[str, Any]:
    from . import s10_query_materializer as m

    c.require(
        1 <= unit_contexts <= ops.PAGE_CONTEXTS, "STAGE10_CHECKPOINT_SIZE_INVALID"
    )
    binding = m.checkpoint_binding(work, executable)
    root = (output_parent or work.root / "shards") / prefix
    root.mkdir(mode=0o700)
    (root / "units").mkdir(mode=0o700)
    index_fd = os.open(
        root / "units.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    after: bytes | None = None
    ordinal = total = 0
    try:
        with os.fdopen(index_fd, "wb") as index:
            while True:
                keys = key_window(work, prefix, after, unit_contexts)
                if not keys and ordinal:
                    break
                unit = root / "units" / f"{ordinal:06}"
                prior = (
                    resume / "units" / f"{ordinal:06}" if resume is not None else None
                )
                if prior is not None and os.path.lexists(prior):
                    pack.regular_private(prior, directory=True)
                if prior is not None and (prior / "checkpoint.json").exists():
                    validate_unit(prior, binding, prefix, keys)
                    shutil.copytree(prior, unit)
                    for directory, _, files in os.walk(unit):
                        Path(directory).chmod(0o700)
                        for name in files:
                            (Path(directory) / name).chmod(0o600)
                    record = validate_unit(unit, binding, prefix, keys)
                    with work.progress.measure("resume_context_reconciliation"):
                        seen = [
                            ctx.identifier
                            for ctx in work.contexts(
                                prefix, after=after, until=keys[-1] if keys else None
                            )
                        ]
                    c.require(
                        seen == keys, "STAGE10_CHECKPOINT_RESUME_MAP_BACK_INVALID"
                    )
                    work.progress.counts["checkpoints_reused"] += 1
                    work.progress.counts["contexts_completed"] += len(keys)
                    work.progress.counts["hypotheses_written"] += record["relations"][
                        0
                    ]["row_count"]
                    work.progress.counts["family_decisions_written"] += record[
                        "relations"
                    ][1]["row_count"]
                else:
                    # An incomplete old unit is preserved, never adopted. Generate
                    # into this new attempt instead; no editing the prior attempt.
                    unit.mkdir(mode=0o700)
                    writers = {
                        name: io.RelationWriter(unit / name, io.output_schema(name))
                        for name in c.RELATIONS
                    }
                    count = 0
                    for context in work.contexts(
                        prefix, after=after, until=keys[-1] if keys else None
                    ):
                        c.require(
                            count < len(keys) and context.identifier == keys[count],
                            "STAGE10_CHECKPOINT_GENERATION_KEYS_INVALID",
                        )
                        with work.progress.measure("family_generation"):
                            generated = families.generate(context, runtime)
                        with work.progress.measure("output_write"):
                            for (name, writer), rows in zip(
                                writers.items(), generated, strict=True
                            ):
                                for row in rows:
                                    io.validate_values(row, name)
                                    io.check_identity(
                                        row,
                                        name,
                                        work.accepted.context_binding,
                                        work.accepted.identifier,
                                        work.science,
                                    )
                                    writer.append(row)
                        count += 1
                        work.progress.counts["contexts_completed"] += 1
                        work.progress.counts["hypotheses_written"] += len(generated[0])
                        work.progress.counts["family_decisions_written"] += len(
                            generated[1]
                        )
                    c.require(
                        count == len(keys), "STAGE10_CHECKPOINT_GENERATION_KEYS_INVALID"
                    )
                    with work.progress.measure("output_close_and_checkpoint"):
                        for writer in writers.values():
                            writer.close()
                        record = {
                            "binding": binding,
                            "prefix": prefix,
                            "context_ids": [k.hex() for k in keys],
                            "relations": [
                                m.relation_record(name, writer.paths, unit, writer.rows)
                                for name, writer in writers.items()
                            ],
                        }
                        base.fsync_tree(unit)
                        io.write_json(unit / "checkpoint.json", record)
                        base.fsync_directory(unit)
                        validate_unit(unit, binding, prefix, keys)
                index.write(
                    c.canonical(
                        {
                            "ordinal": ordinal,
                            "checkpoint_sha256": c.sha256_file(
                                unit / "checkpoint.json"
                            ),
                        }
                    )
                )
                index.flush()
                os.fsync(index.fileno())
                work.progress.counts["checkpoints_completed"] += 1
                work.progress.record(announce=True)
                total += len(keys)
                ordinal += 1
                if not keys:
                    break
                after = keys[-1]
    except BaseException:
        work.progress.record(announce=True)
        raise
    # Coalesce tiny restart units into ordinary bounded-size artifact files.
    # Only this stream enters a future candidate; unit files stay in work space.
    (root / "relations").mkdir(mode=0o700)
    relations = []
    with work.progress.measure("checkpoint_coalesce"):
        for name in c.RELATIONS:
            writer = io.RelationWriter(
                root / "relations" / name, io.output_schema(name)
            )
            for item in index_rows(root):
                unit = root / "units" / f"{item['ordinal']:06}"
                saved = c.read_json(unit / "checkpoint.json")
                record = next(r for r in saved["relations"] if r["name"] == name)
                for row in base.parquet_rows(
                    [unit / f["relative_path"] for f in record["files"]], batch_rows=1
                ):
                    writer.append(row)
            writer.close()
            relations.append(m.relation_record(name, writer.paths, root, writer.rows))
        record = {
            "binding": binding,
            "prefix": prefix,
            "context_count": total,
            "unit_count": ordinal,
            "units_index": m.file_record(root / "units.jsonl", root),
            "relations": relations,
        }
        io.write_json(root / "checkpoint.json", record)
        base.fsync_directory(root)
        validate_prefix(root, binding, prefix)
    return record

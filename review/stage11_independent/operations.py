"""Independent checkpoint, inventory, registration and publication observations."""

import hashlib
import json
import os
import stat
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import oracle as o
from reconcile import rows, scalar


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("DUPLICATE_METADATA_KEY")
            result[k] = v
        return result

    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique)
    if o.canonical(value) != raw:
        raise ValueError("NONCANONICAL_METADATA")
    return value


def private(path, directory=False):
    st = path.lstat()
    return (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)) and (
        stat.S_IMODE(st.st_mode) == (0o700 if directory else 0o600)
        and st.st_uid == os.geteuid()
        and (directory or st.st_nlink == 1)
    )


def tree_inventory(root, check, label):
    result = {}
    check(label + "_root_private", private(root, True))
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            check(label + "_private_directory", private(Path(parent) / name, True))
        for name in files:
            path = Path(parent) / name
            if not private(path):
                check(label + "_private_file", False)
                raise ValueError("UNSAFE_TOPOLOGY")
            check(label + "_private_file", True)
            result[path.relative_to(root).as_posix()] = [
                path.stat().st_size,
                file_sha(path),
            ]
    return result


def files(root, records, check, label):
    paths = []
    for item in records:
        relative = item["relative_path"]
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or any(p in ("", ".", "..") for p in relative.split("/"))
        ):
            raise ValueError("UNSAFE_INVENTORY_PATH")
        path = root / relative
        if path.resolve(strict=True) != path or not private(path):
            raise ValueError("UNSAFE_INVENTORY_TOPOLOGY")
        check(
            label + "_physical_hash",
            file_sha(path) == item["sha256"] and path.stat().st_size == item["bytes"],
        )
        paths.append(path)
    check(label + "_unique_inventory", len(paths) == len(set(paths)))
    return paths


def parquet_sql(paths):
    return (
        "read_parquet(["
        + ",".join("'" + str(p).replace("'", "''") + "'" for p in paths)
        + "])"
    )


def registration(root, manifest, manifest_sha, check):
    inventory = sorted(
        [
            {"path": x["relative_path"], "bytes": x["bytes"], "sha256": x["sha256"]}
            for x in [
                *(f for r in manifest["relations"] for f in r["files"]),
                *manifest["metadata_inventory"],
            ]
        ],
        key=lambda x: x["path"].encode("utf-8"),
    )
    binding = {
        "namespace": "STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG",
        "record_version": "stage11_publication_record_v1",
        "publication_key": root.name,
        "manifest_sha256": manifest_sha,
        "logical_sha256": manifest["logical_sha256"],
        **{
            k: manifest[k]
            for k in ("contract_sha256", "profile_sha256", "schema_bundle_sha256")
        },
        "executable_sha": manifest["operational_provenance"]["execution_git_sha"],
        "stage11_input_binding_sha256": manifest["input_binding_sha256"],
        "encoding_version": "stage11_semantic_request_encoding_v1",
        "stage11_design_sha256": manifest["design_documents_sha256"],
        "stage11_runtime_sha256": hashlib.sha256(
            o.canonical(manifest["runtime"])
        ).hexdigest(),
        "inventory_sha256": hashlib.sha256(o.canonical(inventory)).hexdigest(),
    }
    observed = read_json(root / "_SUCCESS.json")
    body = {"protocol": "exclusive_run_commit_seal_v2_candidate", "bindings": binding}
    # Protocol primitive is reused unchanged; adapter names are Stage 11 only.
    expected = {
        **body,
        "commit_record_id": hashlib.sha256(
            b"SAFE:publication-commit:v2\0" + o.canonical(body)
        ).hexdigest(),
    }
    check("R_exact_registration", observed == expected)
    check(
        "R_exclusive_commit_seal",
        private(root / "_COMMITTED") and (root / "_COMMITTED").stat().st_size == 0,
    )
    check("R_no_in_progress", not (root / "_IN_PROGRESS").exists())
    return expected


def checkpoints(root, manifest, db, check):
    binding = manifest["operational_provenance"]["checkpoint_binding"]
    metrics = manifest["operational_provenance"]["checkpoints"]
    input_count = manifest["relations"][1]["row_count"]
    request_count = manifest["relations"][0]["row_count"]
    all_paths = {"input": [], "reduction": []}
    coverage = {}
    unit_names = []
    spool_schema = pa.schema(
        [
            pa.field("hypothesis_id", pa.binary(32), nullable=False),
            pa.field("query_semantic_id", pa.binary(32), nullable=False),
            pa.field("canonical_bytes", pa.large_binary(), nullable=False),
        ],
        metadata={b"kind": b"STAGE11_OPERATIONAL_CHECKPOINT", b"protected": b"true"},
    )
    total = {"input": 0, "reduction": 0}
    for kind in ("input", "reduction"):
        path = root / (kind + "_coverage.json")
        check("Q_coverage_hash", file_sha(path) == metrics[kind + "_coverage_sha256"])
        coverage[kind] = read_json(path)
        cov = coverage[kind]
        check(
            "Q_coverage_binding",
            cov["binding"] == binding
            and cov["coverage_version"] == f"stage11_{kind}_coverage_v1",
        )
        if kind == "input":
            check("Q_input_coverage_count", cov["hypotheses"] == input_count)
        else:
            check(
                "Q_reduction_contributors",
                cov["contributors_sha256"] == metrics["input_coverage_sha256"],
            )
        previous = None
        for index, entry in enumerate(cov["units"]):
            name = entry["unit"]
            if Path(name).name != name or not name.startswith(kind + "-"):
                raise ValueError("CHECKPOINT_PATH")
            unit_names.append(name)
            unit = root / name
            raw = (unit / "unit.json").read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            check(
                "Q_descriptor_seal",
                (unit / "_COMPLETE").read_bytes() == (digest + "\n").encode("ascii")
                and digest == entry["descriptor_sha256"],
            )
            record = read_json(unit / "unit.json")
            check(
                "Q_unit_exact_binding",
                record["binding"] == binding
                and record["kind"] == kind
                and record["coverage"] == entry["coverage"]
                and record["checkpoint_version"] == "stage11_checkpoint_v1",
            )
            paths = files(unit, record["files"], check, "Q")
            expected_names = {
                "unit.json",
                "_COMPLETE",
                *(f["relative_path"] for f in record["files"]),
            }
            check(
                "Q_unit_exact_inventory",
                {p.relative_to(unit).as_posix() for p in unit.rglob("*") if p.is_file()}
                == expected_names,
            )
            all_paths[kind].extend(paths)
            expected_schema = (
                spool_schema if kind == "input" else o.schema("semantic_request")
            )
            for p in paths:
                check(
                    "Q_payload_schema",
                    pq.read_schema(p).equals(
                        expected_schema, check_metadata=kind == "input"
                    ),
                )
            payload = hashlib.sha256(
                b"SAFE:stage11-checkpoint-payload:v1\0" + o.sequence([kind])
            )
            key_digest = hashlib.sha256(b"SAFE:stage11-input-keys:v1\0")
            n, first, last = 0, None, None
            for p in paths:
                for batch in pq.ParquetFile(
                    p, page_checksum_verification=True
                ).iter_batches(batch_size=1, use_threads=False):
                    row = batch.to_pylist()[0]
                    if kind == "input":
                        key = row["hypothesis_id"]
                        raw_core = row["canonical_bytes"]
                        check(
                            "Q_spool_full_digest",
                            hashlib.sha256(raw_core).digest()
                            == row["query_semantic_id"],
                        )
                        values = [key, row["query_semantic_id"], raw_core]
                        key_digest.update(o.sequence([key]))
                    else:
                        key = row["query_semantic_id"]
                        raw_core = o.core_bytes(row["core"])
                        check(
                            "Q_reduction_full_digest",
                            hashlib.sha256(raw_core).digest() == key,
                        )
                        values = [key, raw_core]
                        check(
                            "Q_prefix_membership",
                            key[: binding["partition_bytes"]].hex()
                            == entry["coverage"]["prefix"],
                        )
                    check("Q_strict_global_order", previous is None or previous < key)
                    previous = last = key
                    if first is None:
                        first = key
                    payload.update(o.sequence(values))
                    n += 1
            payload.update(o.sequence([n]))
            check(
                "Q_payload_hash_count",
                (n, payload.hexdigest()) == (record["rows"], record["payload_sha256"]),
            )
            cv = entry["coverage"]
            if kind == "input":
                check(
                    "Q_input_ranges",
                    cv
                    == {
                        "ordinal": index,
                        "first_hypothesis_id": first.hex(),
                        "last_hypothesis_id": last.hex(),
                        "hypotheses": n,
                        "input_keys_sha256": key_digest.hexdigest(),
                    },
                )
                check(
                    "Q_input_unit_plan",
                    name == f"input-{index:08d}"
                    and n
                    == min(
                        binding["input_unit_rows"],
                        input_count - index * binding["input_unit_rows"],
                    ),
                )
            else:
                check(
                    "Q_reduction_ranges",
                    cv["first_semantic_id"] == first.hex()
                    and cv["last_semantic_id"] == last.hex()
                    and cv["contributors_sha256"] == metrics["input_coverage_sha256"]
                    and entry["requests"] == n,
                )
                check(
                    "Q_reduction_unique_partition", name == "reduction-" + cv["prefix"]
                )
            total[kind] += n
        check("Q_unit_count_" + kind, len(cov["units"]) == metrics[kind + "_units"])
    check(
        "Q_complete_units_only",
        sorted(p.name for p in root.iterdir() if p.is_dir()) == sorted(unit_names)
        and len(set(unit_names)) == len(unit_names),
    )
    check(
        "Q_relation_coverage_totals",
        total == {"input": input_count, "reduction": request_count},
    )
    for kind, view in (
        ("input", "checkpoint_inputs"),
        ("reduction", "checkpoint_requests"),
    ):
        db.execute(
            f"CREATE VIEW {view} AS SELECT * FROM {parquet_sql(all_paths[kind])}"
        )
    for left, right, columns, label in [
        ("checkpoint_inputs", "m", "hypothesis_id,query_semantic_id", "map"),
        ("checkpoint_requests", "s", "query_semantic_id,core", "requests"),
    ]:
        for a, b in ((left, right), (right, left)):
            check(
                "Q_final_exact_" + label,
                scalar(
                    db,
                    f"SELECT count(*) FROM (SELECT {columns} FROM {a} EXCEPT ALL SELECT {columns} FROM {b})",
                )
                == 0,
            )
    mismatch, visited = 0, 0
    for row in rows(
        db,
        "SELECT c.canonical_bytes,h.intent,h.selection_status FROM checkpoint_inputs c JOIN h USING(hypothesis_id)",
    ):
        mismatch += row["canonical_bytes"] != o.core_bytes(
            o.project(row["intent"], row["selection_status"])
        )
        visited += 1
    check("Q_every_input_payload_projection", mismatch == 0 and visited == input_count)
    counts = dict(
        db.execute(
            f"SELECT lower(substr(hex(query_semantic_id),1,{2 * binding['partition_bytes']})),count(*) FROM m GROUP BY 1"
        ).fetchall()
    )
    check(
        "Q_reduction_membership_coverage",
        all(
            e["coverage"]["hypotheses"] == counts[e["coverage"]["prefix"]]
            for e in coverage["reduction"]["units"]
        ),
    )
    return {
        "input_units": len(coverage["input"]["units"]),
        "reduction_units": len(coverage["reduction"]["units"]),
        "seals": len(unit_names),
        "incomplete_units": len(list(root.glob("*/unit.json")))
        - len(list(root.glob("*/_COMPLETE"))),
    }

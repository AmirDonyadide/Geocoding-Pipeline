"""Invented Stage 10 inputs with exact upstream identities and family lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as s10
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as s10io
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_input as source


def write(path: Path, rows: list[dict[str, Any]], schema: Any) -> None:
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd")
    path.chmod(0o600)


def fixture(
    root: Path,
    *,
    contexts: int = 8,
    text: str = "Invented avenue 1\nCafé",
    reverse: bool = False,
    varied: bool = False,
    structured: bool = True,
    empty_context: bool = True,
    varied_boundary: bool = True,
) -> source.Inputs:
    root.mkdir(mode=0o700)
    args = tuple(s10.identity("synthetic-stage11:v1", i) for i in range(3))
    hs, ds = [], []
    for i in range(contexts):
        role = "STANDARD" if i % 2 == 0 else "NATIVE"
        source_id = s10.identity("synthetic-source:v1", i // 2)
        candidate = s10.identity("synthetic-candidate:v1", i)
        context = s10.context_id(args[0], source_id, role)
        intents = (
            []
            if empty_context and i == contexts - 1
            else [
                s10.full_intent(
                    text + (f" {i // 2}" if varied else ""),
                    "FR" if varied_boundary and i == contexts - 2 else "DE",
                )
            ]
        )
        if structured and i == 0:
            structured_intent = s10.full_intent("", "DE")
            structured_intent.update(
                endpoint="/v1/search/structured",
                search_mode="STRUCTURED",
                text=None,
                address=text,
                postalcode="00123",
                locality=None,
            )
            intents.append(structured_intent)
        members = []
        for rank, intent in enumerate(intents, 1):
            representation = s10.intent_fingerprint(intent)
            hid = s10.identity(
                "stage10-hypothesis:v1", args[1], args[2], context, representation
            )
            hs.append(
                {
                    "hypothesis_id": hid,
                    "query_context_id": context,
                    "stable_source_row_id_v1": source_id,
                    "stage08_representation": role,
                    "stage06_exact_candidate_id": candidate,
                    "representation_fingerprint": representation,
                    "intent": intent,
                    "generation_rank": rank,
                    "selection_status": s10.MODE,
                }
            )
            members.append(hid)
        for family in s10.FAMILIES:
            hid, membership = None, "NONE"
            if members and family in (("Q1" if role == "STANDARD" else "Q2"), "Q3"):
                hid = members[0]
                membership = "CONVERGENT_MEMBER" if family == "Q3" else "FIRST_MEMBER"
            if family == "Q4" and len(members) == 2:
                hid, membership = members[1], "FIRST_MEMBER"
            ds.append(
                {
                    "query_context_id": context,
                    "hypothesis_id": hid,
                    "family": family,
                    "eligibility_state": "ELIGIBLE"
                    if hid is not None
                    else "INELIGIBLE",
                    "membership_state": membership,
                    "stable_source_row_id_v1": source_id,
                    "stage08_representation": role,
                    "stage06_exact_candidate_id": candidate,
                }
            )
    d_schema = pa.schema(
        [s10.schema("query_family_decision").field(k) for k in source.DECISION_COLUMNS]
    )
    write(
        root / "h.parquet",
        list(reversed(hs)) if reverse else hs,
        s10io.output_schema("query_hypothesis"),
    )
    write(root / "d.parquet", list(reversed(ds)) if reverse else ds, d_schema)
    digest = s10io.relation_fingerprint(
        "query_hypothesis",
        len(hs),
        sorted(
            hs, key=lambda r: (r["query_context_id"], r["representation_fingerprint"])
        ),
    ).hex()
    population = {
        "hypotheses": len(hs),
        "sources": (contexts + 1) // 2,
        "contexts": contexts,
        "standard_contexts": (contexts + 1) // 2,
        "native_contexts": contexts // 2,
        "decisions": len(ds),
        "zero_hypothesis_contexts": int(empty_context),
        "eligible_family_links": sum(d["hypothesis_id"] is not None for d in ds),
    }
    # Synthetic identity binds logical input and a fixed invented scope. Different
    # fixture layout tests hold that scope fixed; protected bindings also pin files.
    binding = {
        "binding_version": "SYNTHETIC_ONLY",
        "hypothesis_sha256": digest,
        "decision_sha256": s10.identity(
            "synthetic-decisions:v1",
            c.canonical(
                [
                    {k: v.hex() if isinstance(v, bytes) else v for k, v in d.items()}
                    for d in ds
                ]
            ),
        ).hex(),
    }
    return source.Inputs(
        (root / "h.parquet",), (root / "d.parquet",), binding, population, digest, args
    )

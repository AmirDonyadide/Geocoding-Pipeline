"""Exact accepted Stage 10 projection; never opens transitive source payloads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from . import s10_query_contract as upstream
from . import s10_query_io as upstream_io
from . import s10_query_publication as upstream_publication
from . import s11_semantic_contract as c
from . import s11_semantic_io as io

PROJECT = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
PUBLICATION = "stage10_development_20260928T081247Z_cf9e0fe4c12e"
ROOT = PROJECT / "derived/controlled/stage10/development" / PUBLICATION
MANIFEST_SHA = "558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860"
HYPOTHESIS_SHA = "c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1"
DECISION_COLUMNS = (
    "query_context_id",
    "hypothesis_id",
    "family",
    "eligibility_state",
    "membership_state",
    "stable_source_row_id_v1",
    "stage08_representation",
    "stage06_exact_candidate_id",
)
POPULATION = {
    "hypotheses": 142677,
    "sources": 35000,
    "contexts": 69747,
    "standard_contexts": 34822,
    "native_contexts": 34925,
    "decisions": 418482,
    "zero_hypothesis_contexts": 1668,
    "eligible_family_links": 172112,
}


@dataclass(frozen=True)
class Inputs:
    hypotheses: tuple[Path, ...]
    decisions: tuple[Path, ...]
    binding: Mapping[str, Any]
    population: Mapping[str, int]
    hypothesis_sha: str
    identity_arguments: tuple[bytes, bytes, bytes]

    @property
    def identifier(self) -> bytes:
        return c.identity("stage11-input:v1", c.canonical(self.binding))

    def register(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            f"CREATE VIEW h AS SELECT * FROM {io.parquet_sql(self.hypotheses)}"
        )
        connection.execute(
            f"CREATE VIEW d AS SELECT {','.join(DECISION_COLUMNS)} FROM {io.parquet_sql(self.decisions)}"
        )


def input_asset(
    manifest: Mapping[str, Any], asset_ids: Mapping[str, str]
) -> dict[str, Any]:
    return {
        "binding_version": "stage11_input_binding_v1",
        "split": "DEVELOPMENT",
        "benchmark_sha256": manifest["input_binding"]["benchmark_sha256"],
        "stage10": {
            "approved_anchor": str(ROOT),
            "publication_key": PUBLICATION,
            "manifest_sha256": MANIFEST_SHA,
            "acceptance_sha": "d027da6c504a8fe864a7821a3e786c390ec05add",
            "acceptance_tag": "stage10-multi-hypothesis-query-generation-v1",
            "execution_git_sha": "cf9e0fe4c12eb85f78051904c636ad084d87a541",
            **{
                k: manifest[k]
                for k in (
                    "logical_sha256",
                    "contract_sha256",
                    "profile_sha256",
                    "schema_bundle_sha256",
                    "input_binding_sha256",
                    "science_sha256",
                )
            },
            "relations": manifest["relations"],
            "metadata_inventory": manifest["metadata_inventory"],
            "transitive_input_binding": manifest["input_binding"],
        },
        "read_projection": {
            "query_hypothesis": upstream.schema("query_hypothesis").names,
            "query_family_decision": list(DECISION_COLUMNS),
        },
        "population": POPULATION,
        "stage11_design_sha": c.DESIGN_SHA,
        "stage11_design_tag": c.DESIGN_TAG,
        "stage11_assets": dict(asset_ids),
    }


def load_accepted(repository: Path, asset_ids: Mapping[str, str]) -> Inputs:
    require_goethe_nhr_slurm(
        "stage11_semantic_request_deduplication"
    )  # Before protected path stat.
    manifest = upstream_publication.validate_terminal(ROOT, MANIFEST_SHA, True)
    expected = c.decode_json(
        (
            repository / "docs/scientific_assets/stage11_input_binding_v1.json"
        ).read_bytes()
    )
    binding = input_asset(manifest, asset_ids)
    c.require(
        binding == expected
        and manifest["split"] == "DEVELOPMENT"
        and manifest["plan_mode"] == "ALL_ELIGIBLE_CATALOG"
        and manifest["operating_budget"] is None,
        "S11_INPUT_BINDING_INVALID",
    )
    paths: dict[str, tuple[Path, ...]] = {}
    for relation in manifest["relations"]:
        name = relation["name"]
        c.require(
            name in upstream.RELATIONS
            and relation["schema_sha256"] == upstream.schema_fingerprint(name).hex(),
            "S11_INPUT_BINDING_INVALID",
        )
        checked = []
        for item in relation["files"]:
            path = io.verify_file(ROOT, item)
            c.require(
                pq.read_schema(path).equals(
                    upstream_io.output_schema(name), check_metadata=True
                ),
                "S11_INPUT_BINDING_INVALID",
            )
            checked.append(path)
        paths[name] = tuple(checked)
    for item in manifest["metadata_inventory"]:
        io.verify_file(ROOT, item)
    c.require(
        [r["row_count"] for r in manifest["relations"]] == [142677, 418482]
        and manifest["relations"][0]["logical_sha256"] == HYPOTHESIS_SHA,
        "S11_INPUT_BINDING_INVALID",
    )
    transitive = manifest["input_binding"]
    arguments = (
        upstream.identity(
            "stage10-context-input:v1",
            *(
                bytes.fromhex(transitive[k]["manifest_sha256"])
                for k in ("stage08", "stage06_row_map", "stage09")
            ),
        ),
        bytes.fromhex(manifest["input_binding_sha256"]),
        bytes.fromhex(manifest["science_sha256"]),
    )
    return Inputs(
        paths["query_hypothesis"],
        paths["query_family_decision"],
        binding,
        POPULATION,
        HYPOTHESIS_SHA,
        arguments,
    )


def validate(inputs: Inputs, connection: duckdb.DuckDBPyConnection) -> None:
    def checked() -> Any:
        for row in io.rows(
            connection,
            "SELECT * FROM h ORDER BY query_context_id,representation_fingerprint",
        ):
            c.project(row["intent"], row["selection_status"])
            try:
                upstream_io.validate_values(row, "query_hypothesis")
                upstream_io.check_identity(
                    row, "query_hypothesis", *inputs.identity_arguments
                )
            except upstream.Stage10Error as error:
                raise c.Stage11Error("S11_UPSTREAM_ID_INVALID") from error
            yield row

    digest = upstream_io.relation_fingerprint(
        "query_hypothesis", inputs.population["hypotheses"], checked()
    )
    c.require(digest.hex() == inputs.hypothesis_sha, "S11_INPUT_BINDING_INVALID")
    count, distinct = connection.execute(
        "SELECT count(*),count(DISTINCT hypothesis_id) FROM h"
    ).fetchone() or (None, None)
    c.require(
        count == distinct == inputs.population["hypotheses"], "S11_UPSTREAM_ID_INVALID"
    )
    # No certificate fields are selected from d. Complete input file hashes were
    # verified above; accepted Stage 10 scientific generation is not rerun.
    bad = connection.execute("""SELECT count(*) FROM d WHERE
        query_context_id IS NULL OR stable_source_row_id_v1 IS NULL OR stage06_exact_candidate_id IS NULL
        OR stage08_representation IS NULL OR family IS NULL OR eligibility_state IS NULL OR membership_state IS NULL
        OR stage08_representation NOT IN ('STANDARD','NATIVE')
        OR family NOT IN ('Q1','Q2','Q3','Q4','Q5','Q6')
        OR eligibility_state NOT IN ('ELIGIBLE','INELIGIBLE')
        OR NOT ((eligibility_state='ELIGIBLE' AND membership_state IN ('FIRST_MEMBER','CONVERGENT_MEMBER')
            AND hypothesis_id IS NOT NULL) OR
            (eligibility_state='INELIGIBLE' AND membership_state='NONE' AND hypothesis_id IS NULL))""").fetchone()
    c.require(bad == (0,), "S11_UPSTREAM_ID_INVALID")
    c.require(
        connection.execute(
            "SELECT count(*) FROM (SELECT query_context_id,family FROM d GROUP BY ALL HAVING count(*)<>1)"
        ).fetchone()
        == (0,),
        "S11_UPSTREAM_ID_INVALID",
    )
    c.require(
        connection.execute("""SELECT count(*) FROM (
        SELECT query_context_id FROM d GROUP BY query_context_id HAVING count(*)<>6
        OR count(DISTINCT (stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id))<>1
    )""").fetchone()
        == (0,),
        "S11_UPSTREAM_ID_INVALID",
    )
    c.require(
        connection.execute("""SELECT count(*) FROM d LEFT JOIN h
        ON d.hypothesis_id=h.hypothesis_id AND d.query_context_id=h.query_context_id
        AND d.stable_source_row_id_v1=h.stable_source_row_id_v1
        AND d.stage08_representation=h.stage08_representation
        AND d.stage06_exact_candidate_id=h.stage06_exact_candidate_id
        WHERE d.eligibility_state='ELIGIBLE' AND h.hypothesis_id IS NULL""").fetchone()
        == (0,),
        "S11_UPSTREAM_ID_INVALID",
    )
    c.require(
        connection.execute("""SELECT count(*) FROM (
        SELECT h.hypothesis_id FROM h LEFT JOIN d ON h.hypothesis_id=d.hypothesis_id
        AND h.query_context_id=d.query_context_id AND d.membership_state='FIRST_MEMBER'
        GROUP BY h.hypothesis_id HAVING count(d.hypothesis_id)<>1)""").fetchone()
        == (0,),
        "S11_UPSTREAM_ID_INVALID",
    )
    observed = connection.execute("""SELECT count(*),count(DISTINCT query_context_id),
        count(DISTINCT stable_source_row_id_v1),
        count(DISTINCT query_context_id) FILTER(WHERE stage08_representation='STANDARD'),
        count(DISTINCT query_context_id) FILTER(WHERE stage08_representation='NATIVE'),
        count(*) FILTER(WHERE eligibility_state='ELIGIBLE') FROM d""").fetchone()
    p = inputs.population
    c.require(
        observed
        == (
            p["decisions"],
            p["contexts"],
            p["sources"],
            p["standard_contexts"],
            p["native_contexts"],
            p["eligible_family_links"],
        ),
        "S11_INPUT_BINDING_INVALID",
    )
    c.require(
        connection.execute("""SELECT count(*) FROM (SELECT DISTINCT query_context_id FROM d
        EXCEPT SELECT query_context_id FROM h)""").fetchone()
        == (p["zero_hypothesis_contexts"],),
        "S11_INPUT_BINDING_INVALID",
    )

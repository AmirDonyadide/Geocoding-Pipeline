"""Campaign-wide verified history and bounded four-relation integrity checks.

These interfaces consume controlled receipts/IDs, not protected query payloads.
Callers must pin the complete workload and closed deployment intervals before
publication. Incomplete history consumes budget but never supplies candidates.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import s12_campaign as campaign
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io


@dataclass(frozen=True)
class HistoryUnit:
    path: Path
    evidence_sha256: bytes
    closure_sha256: bytes
    complete: bool


def history(
    units: Iterable[HistoryUnit],
    binding: Mapping[str, str],
    *,
    reopen: Callable[[bytes, dict[str, Any]], response.Projection],
) -> tuple[list[dict[str, Any]], Path | None]:
    """Ordered externally pinned units; UNKNOWN_DELIVERY is never adopted.

    An incomplete unit is pinned by its begin receipt. Later files do not make
    it adoptable; recovery must have separately closed its verification interval.
    """
    io.validate_binding(binding)
    attempts: list[dict[str, Any]] = []
    selected = None
    for unit in units:
        c.digest(unit.closure_sha256)
        c.require(
            io.read(unit.path / "binding.json") == c.canonical(dict(binding)),
            "S12_CHECKPOINT_BINDING_MISMATCH",
        )
        if unit.complete:
            c.require(
                c.sha(io.read(unit.path / "receipt.json"))
                == c.digest(unit.evidence_sha256),
                "S12_CHECKPOINT_RECEIPT_MISMATCH",
            )
            row, _, _ = io.validate(
                unit.path, binding, reopen=reopen, require_success=False
            )
        else:
            raw = io.read(unit.path / "begin.parquet")
            c.require(
                c.sha(raw) == c.digest(unit.evidence_sha256),
                "S12_CHECKPOINT_RECEIPT_MISMATCH",
            )
            rows = io.read_rows(raw, "request_attempt")
            c.require(len(rows) == 1, "S12_ATTEMPT_HISTORY_INVALID")
            row = rows[0]
            io.validate_begin(binding, row)
        attempts.append(row)
        campaign.reconcile_attempts(
            attempts,
            bytes.fromhex(binding["campaign_id"]),
            bytes.fromhex(binding["request_execution_id"]),
        )
        if row["outcome"] in c.SUCCESS:
            selected = unit.path
    return attempts, selected


Rows = Callable[[str], Iterable[dict[str, Any]]]


def relations(
    rows: Rows, expected_semantic_ids: frozenset[bytes], *, campaign_id: bytes
) -> dict[str, str | int]:
    """Full PK/FK/rank/count/outcome/binding validation without candidate accumulation.

    Only execution summaries, attempt selection and policy IDs remain in memory.
    Rows factories reopen immutable relations for each streaming digest pass.
    """
    policies = {}
    counts: dict[str, int] = {name: 0 for name in c.RELATIONS}
    for row in rows("retrieval_policy"):
        c.validate_policy(row)
        c.require(row["retrieval_policy_id"] not in policies, "S12_DUPLICATE_POLICY")
        policies[row["retrieval_policy_id"]] = row["result_limit"]
        counts["retrieval_policy"] += 1
    executions = {}
    semantics: set[bytes] = set()
    for row in rows("request_execution"):
        c.row_bytes("request_execution", row)
        execution = row["request_execution_id"]
        c.require(
            execution not in executions and row["query_semantic_id"] not in semantics,
            "S12_DUPLICATE_EXECUTION",
        )
        core = {
            k: c.IDENTITY if k == "identity_version" else row[k]
            for k in c.EXECUTION_FIELDS
        }
        c.require(
            c.execution_id(core) == execution
            and row["retrieval_policy_id"] in policies,
            "S12_EXECUTION_BINDING_INVALID",
        )
        c.require(
            row["terminal_state"] in c.SUCCESS
            and type(row["candidate_count"]) is int
            and 0 <= row["candidate_count"] <= policies[row["retrieval_policy_id"]],
            "S12_PUBLICATION_INCOMPLETE",
        )
        c.require(
            (row["terminal_state"] == "SUCCESS_ZERO_CANDIDATES")
            == (row["candidate_count"] == 0),
            "S12_CANDIDATE_COUNT_INVALID",
        )
        c.digest(row["response_sha256"])
        c.require(
            row["response_bytes"] is not None and row["response_bytes"] > 0,
            "S12_CAPTURE_INCOMPLETE",
        )
        executions[execution] = row
        semantics.add(row["query_semantic_id"])
        counts["request_execution"] += 1
    c.require(semantics == expected_semantic_ids, "S12_WORKLOAD_TOTALITY_INVALID")
    histories: dict[bytes, list[dict[str, Any]]] = {}
    # Attempt relation is sorted by attempt_id, not ordinal; bounded <=5 per ID.
    for row in rows("request_attempt"):
        c.row_bytes("request_attempt", row)
        execution = row["request_execution_id"]
        c.require(execution in executions, "S12_FOREIGN_KEY_INVALID")
        history_rows = histories.setdefault(execution, [])
        history_rows.append(row)
        c.require(len(history_rows) <= 5, "S12_ATTEMPT_HISTORY_INVALID")
        counts["request_attempt"] += 1
    for execution, row in executions.items():
        history_rows = sorted(
            histories.get(execution, []), key=lambda item: item["attempt_number"]
        )
        _, selected = campaign.reconcile_attempts(history_rows, campaign_id, execution)
        c.require(
            bool(history_rows) and selected == row["response_sha256"],
            "S12_ATTEMPT_HISTORY_INVALID",
        )
        last = history_rows[-1]
        c.require(
            last["attempt_id"] == row["terminal_attempt_id"]
            and last["outcome"] == row["terminal_state"]
            and last["application_payload_bytes"] == row["response_bytes"],
            "S12_ATTEMPT_HISTORY_INVALID",
        )
    ranks: dict[bytes, int] = {}
    for row in rows("request_candidate"):
        c.row_bytes("request_candidate", row)
        execution = row["request_execution_id"]
        c.require(execution in executions, "S12_FOREIGN_KEY_INVALID")
        expected_rank = ranks.get(execution, 0) + 1
        c.require(row["rank"] == expected_rank, "S12_CANDIDATE_RANK_INVALID")
        c.require(
            row["response_sha256"] == executions[execution]["response_sha256"],
            "S12_RAW_HASH_MISMATCH",
        )
        ranks[execution] = expected_rank
        counts["request_candidate"] += 1
    c.require(
        all(
            ranks.get(key, 0) == row["candidate_count"]
            for key, row in executions.items()
        ),
        "S12_CANDIDATE_COUNT_INVALID",
    )
    result: dict[str, str | int] = {}
    for name in c.RELATIONS:
        result[name + "_count"] = counts[name]
        result[name + "_sha256"] = c.relation_hash(name, counts[name], rows(name)).hex()
        if name != "request_attempt":
            result[name + "_scientific_sha256"] = c.relation_hash(
                name, counts[name], rows(name), scientific=True
            ).hex()
    return result

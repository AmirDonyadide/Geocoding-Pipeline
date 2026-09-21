"""Temporary aggregate-only instrumentation for the confirmation allocation.

Every wrapper delegates unchanged arguments/results. No cache lookup or
scientific decision is added. Labels are fixed; SQL/values/identities never log.
"""

from __future__ import annotations

import time
from contextlib import ExitStack, contextmanager
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

from .stages import s10_query_checkpoints as units
from .stages import s10_query_contexts as cx
from .stages import s10_query_contract as c
from .stages import s10_query_io as io
from .stages import s10_query_operations as ops

COUNTERS = (
    "registry_encode_count",
    "selector_add_attempts",
    "selector_buffer_insertions",
    "selector_sql_insertions",
    "parser_certificate_preparation_calls",
    "explicit_transaction_begins",
    "explicit_transaction_commits",
    "explicit_transaction_rollbacks",
    "database_checkpoints_completed",
)


def initialize(progress: ops.Progress) -> None:
    for name in COUNTERS:
        progress.counts.setdefault(name, 0)


@contextmanager
def instrument(work: cx.ContextWorkspace) -> Iterator[None]:
    active_relation: str | None = None
    transaction_start: int | None = None
    material = cx.ReferenceAccess._material
    encode = cx.encoded
    selector_add = ops.SelectorAccumulator.add
    execute = ops.TimedConnection.execute
    checkpoint = cx.ContextWorkspace.checkpoint_database
    parser_preparation = cx.ContextWorkspace.prepare_parser_certificates

    def increment(name: str) -> None:
        work.progress.counts[name] = work.progress.counts.get(name, 0) + 1

    def timed(function: Any, label: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            with work.progress.measure(label):
                return function(*args, **kwargs)

        return call

    def read_material(self: Any, name: str, key: str, identifier: bytes) -> Any:
        nonlocal active_relation
        previous, active_relation = active_relation, name
        try:
            return material(self, name, key, identifier)
        finally:
            active_relation = previous

    def encoded(values: Any) -> bytes:
        if active_relation == "registry":
            increment("registry_encode_count")
        with work.progress.measure("certificate_serialization"):
            return encode(values)

    def add(self: Any, section: int, key: bytes, payload: bytes) -> None:
        increment("selector_add_attempts")
        # Inspect membership only; do not mutate the set or touch LRU state.
        if (section, key) not in self.items:
            increment("selector_buffer_insertions")
        selector_add(self, section, key, payload)

    def sql(self: Any, query: str, parameters: Any = None) -> Any:
        nonlocal transaction_start
        result = execute(self, query, parameters)
        operation = query.strip().upper()
        if operation.startswith("INSERT INTO SELECTOR_SELECTION"):
            increment("selector_sql_insertions")
        if operation == "BEGIN TRANSACTION":
            increment("explicit_transaction_begins")
            transaction_start = time.monotonic_ns()
        elif operation in ("COMMIT", "ROLLBACK"):
            increment(
                "explicit_transaction_commits"
                if operation == "COMMIT"
                else "explicit_transaction_rollbacks"
            )
            if transaction_start is not None:
                elapsed = time.monotonic_ns() - transaction_start
                observed = work.progress.observations
                observed["explicit_transaction_max_ns"] = max(
                    observed.get("explicit_transaction_max_ns", 0), elapsed
                )
                transaction_start = None
        return result

    def checkpoint_database(self: Any) -> None:
        before = self.progress.observe_wal(self.root / "context.duckdb")
        checkpoint(self)  # Retains the original fail-closed WAL-zero assertion.
        after = self.progress.observe_wal(self.root / "context.duckdb")
        increment("database_checkpoints_completed")
        self.progress.observations.update(
            wal_before_checkpoint_bytes=before,
            wal_after_checkpoint_bytes=after,
            database_bytes=(self.root / "context.duckdb").stat().st_size,
        )

    def prepare_parser(self: Any) -> None:
        increment("parser_certificate_preparation_calls")
        parser_preparation(self)

    initialize(work.progress)
    with ExitStack() as stack:
        for owner, name, replacement in (
            (cx.ReferenceAccess, "_material", read_material),
            (cx, "encoded", encoded),
            (ops.SelectorAccumulator, "add", add),
            (ops.TimedConnection, "execute", sql),
            (cx.ContextWorkspace, "checkpoint_database", checkpoint_database),
            (cx.ContextWorkspace, "prepare_parser_certificates", prepare_parser),
            (c, "identity", timed(c.identity, "identity_hashing")),
            (
                io.RelationWriter,
                "append",
                timed(io.RelationWriter.append, "serialization_append"),
            ),
            (
                io.RelationWriter,
                "close",
                timed(io.RelationWriter.close, "serialization_close_fsync"),
            ),
            (
                units,
                "validate_unit",
                timed(units.validate_unit, "checkpoint_unit_validation"),
            ),
            (
                units,
                "validate_prefix",
                timed(units.validate_prefix, "checkpoint_prefix_validation"),
            ),
        ):
            stack.enter_context(patch.object(owner, name, replacement))
        yield

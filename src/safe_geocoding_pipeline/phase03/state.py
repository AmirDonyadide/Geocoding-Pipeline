from __future__ import annotations

import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import FILE_STATUSES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Phase03RunState:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        self.connection = sqlite3.connect(path)
        path.chmod(0o600)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        statuses = ",".join(f"'{status}'" for status in FILE_STATUSES)
        self.connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS run_meta(
                key TEXT COLLATE BINARY PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS shard_state(
                relative_path TEXT COLLATE BINARY PRIMARY KEY,
                phase02_output_sha256 TEXT NOT NULL,
                configuration_fingerprint TEXT NOT NULL,
                implementation_fingerprint TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL CHECK(status IN ({statuses})),
                temporary_core_path TEXT NOT NULL DEFAULT '',
                temporary_evidence_path TEXT NOT NULL DEFAULT '',
                final_core_path TEXT NOT NULL DEFAULT '',
                final_evidence_path TEXT NOT NULL DEFAULT '',
                core_semantic_digest TEXT NOT NULL DEFAULT '',
                evidence_semantic_digest TEXT NOT NULL DEFAULT '',
                core_output_sha256 TEXT NOT NULL DEFAULT '',
                evidence_output_sha256 TEXT NOT NULL DEFAULT '',
                failure_code TEXT NOT NULL DEFAULT '',
                updated_at_utc TEXT NOT NULL
            ) WITHOUT ROWID;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.connection.close()

    def __enter__(self) -> "Phase03RunState":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def prepare_shard(
        self,
        relative_path: str,
        *,
        phase02_output_sha256: str,
        configuration_fingerprint: str,
        implementation_fingerprint: str,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO shard_state(
                    relative_path, phase02_output_sha256, configuration_fingerprint,
                    implementation_fingerprint, status, updated_at_utc
                ) VALUES (?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    relative_path,
                    phase02_output_sha256,
                    configuration_fingerprint,
                    implementation_fingerprint,
                    _now(),
                ),
            )
        row = self.get(relative_path)
        if any(
            row[key] != expected
            for key, expected in {
                "phase02_output_sha256": phase02_output_sha256,
                "configuration_fingerprint": configuration_fingerprint,
                "implementation_fingerprint": implementation_fingerprint,
            }.items()
        ):
            raise RuntimeError("resumed Phase 3 shard identity changed")

    def transition(self, relative_path: str, status: str, **values: str | int) -> None:
        if status not in FILE_STATUSES:
            raise ValueError("invalid Phase 3 state")
        allowed = {
            "attempt",
            "temporary_core_path",
            "temporary_evidence_path",
            "final_core_path",
            "final_evidence_path",
            "core_semantic_digest",
            "evidence_semantic_digest",
            "core_output_sha256",
            "evidence_output_sha256",
            "failure_code",
        }
        if not set(values).issubset(allowed):
            raise ValueError("unsupported state field")
        current_row = self.get(relative_path)
        current = current_row["status"]
        allowed_transitions = {
            "PENDING": {"WRITING", "FAILED"},
            "WRITING": {"VALIDATING", "FAILED"},
            "VALIDATING": {"COMPLETE", "FAILED"},
            "FAILED": {"WRITING", "FAILED"},
            "COMPLETE": {"COMPLETE"},
        }
        if status not in allowed_transitions[current]:
            raise ValueError(f"invalid Phase 3 state transition: {current} -> {status}")
        prospective = {**current_row, **values, "status": status}
        if status == "WRITING" and (
            int(prospective["attempt"]) < 1
            or not prospective["temporary_core_path"]
            or not prospective["temporary_evidence_path"]
        ):
            raise ValueError("WRITING state requires attempt and temporary paths")
        if status == "COMPLETE":
            required = (
                "final_core_path",
                "final_evidence_path",
                "core_semantic_digest",
                "evidence_semantic_digest",
                "core_output_sha256",
                "evidence_output_sha256",
            )
            if any(not prospective[field] for field in required):
                raise ValueError("COMPLETE state requires validated output identity")
            for field in required[2:]:
                value = prospective[field]
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or value != value.lower()
                ):
                    raise ValueError("COMPLETE digest identity must be SHA-256 hex")
                try:
                    bytes.fromhex(value)
                except ValueError as error:
                    raise ValueError(
                        "COMPLETE digest identity must be SHA-256 hex"
                    ) from error
        if (
            status == "FAILED"
            and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", str(prospective["failure_code"]))
            is None
        ):
            raise ValueError("FAILED state requires a privacy-safe failure code")
        assignments = ["status=?", "updated_at_utc=?"] + [f"{key}=?" for key in values]
        parameters: list[str | int] = [status, _now(), *values.values(), relative_path]
        with self.connection:
            cursor = self.connection.execute(
                f"UPDATE shard_state SET {', '.join(assignments)} WHERE relative_path=?",
                parameters,
            )
        if cursor.rowcount != 1:
            raise KeyError(relative_path)

    def get(self, relative_path: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM shard_state WHERE relative_path=?", (relative_path,)
        ).fetchone()
        if row is None:
            raise KeyError(relative_path)
        return dict(row)

    def integrity_check(self) -> str:
        return str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])

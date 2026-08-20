from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import FILE_STATUSES
from .models import Phase01FileEntry


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RunState:
    """Small durable state store for file-level Phase 2 restartability."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        path.chmod(0o600)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.execute("PRAGMA busy_timeout=5000")
        statuses = ",".join(f"'{status}'" for status in FILE_STATUSES)
        self.connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS run_meta (
                key TEXT COLLATE BINARY PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS file_state (
                relative_path TEXT COLLATE BINARY PRIMARY KEY,
                source_sha256 TEXT NOT NULL,
                expected_size_bytes INTEGER NOT NULL,
                expected_rows INTEGER NOT NULL,
                config_fingerprint TEXT NOT NULL,
                implementation_fingerprint TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL CHECK(status IN ({statuses})),
                temporary_path TEXT NOT NULL DEFAULT '',
                final_path TEXT NOT NULL DEFAULT '',
                source_semantic_digest TEXT NOT NULL DEFAULT '',
                staging_semantic_digest TEXT NOT NULL DEFAULT '',
                output_sha256 TEXT NOT NULL DEFAULT '',
                output_size_bytes INTEGER NOT NULL DEFAULT 0,
                source_rows INTEGER NOT NULL DEFAULT 0,
                staging_rows INTEGER NOT NULL DEFAULT 0,
                validation_json TEXT NOT NULL DEFAULT '{{}}',
                failure_code TEXT NOT NULL DEFAULT '',
                failure_detail TEXT NOT NULL DEFAULT '',
                started_at_utc TEXT NOT NULL DEFAULT '',
                updated_at_utc TEXT NOT NULL,
                completed_at_utc TEXT NOT NULL DEFAULT ''
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS attempt_history (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                relative_path TEXT COLLATE BINARY NOT NULL,
                attempt INTEGER NOT NULL,
                started_at_utc TEXT NOT NULL,
                completed_at_utc TEXT NOT NULL DEFAULT '',
                terminal_status TEXT NOT NULL DEFAULT '',
                failure_code TEXT NOT NULL DEFAULT '',
                temporary_path TEXT NOT NULL DEFAULT '',
                output_sha256 TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(relative_path) REFERENCES file_state(relative_path),
                UNIQUE(relative_path, attempt)
            );
            """
        )
        self.connection.commit()

    def __enter__(self) -> "RunState":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.connection.close()

    def set_meta(self, key: str, value: str) -> None:
        existing = self.connection.execute(
            "SELECT value FROM run_meta WHERE key = ?", (key,)
        ).fetchone()
        if existing is not None and existing["value"] != value:
            raise RuntimeError(f"Resumed run metadata mismatch: {key}")
        self.connection.execute(
            "INSERT OR IGNORE INTO run_meta(key, value) VALUES (?, ?)", (key, value)
        )
        self.connection.commit()

    def prepare_files(
        self,
        entries: list[Phase01FileEntry],
        *,
        config_fingerprint: str,
        implementation_fingerprint: str,
    ) -> None:
        existing_rows = self.rows()
        if existing_rows:
            self._validate_existing_population(
                existing_rows,
                entries,
                config_fingerprint=config_fingerprint,
                implementation_fingerprint=implementation_fingerprint,
            )
            return
        now = _utc_now()
        with self.connection:
            for entry in entries:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO file_state(
                        relative_path, source_sha256, expected_size_bytes, expected_rows,
                        config_fingerprint, implementation_fingerprint, status, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (
                        entry.relative_path,
                        entry.sha256,
                        entry.size_bytes,
                        entry.logical_record_count,
                        config_fingerprint,
                        implementation_fingerprint,
                        now,
                    ),
                )
        self._validate_existing_population(
            self.rows(),
            entries,
            config_fingerprint=config_fingerprint,
            implementation_fingerprint=implementation_fingerprint,
        )

    @staticmethod
    def _validate_existing_population(
        rows: list[dict[str, Any]],
        entries: list[Phase01FileEntry],
        *,
        config_fingerprint: str,
        implementation_fingerprint: str,
    ) -> None:
        if {row["relative_path"] for row in rows} != {
            entry.relative_path for entry in entries
        }:
            raise RuntimeError("Resumed run file scope differs from original run")
        entries_by_path = {entry.relative_path: entry for entry in entries}
        for row in rows:
            entry = entries_by_path[row["relative_path"]]
            if (
                row["source_sha256"] != entry.sha256
                or row["expected_size_bytes"] != entry.size_bytes
                or row["expected_rows"] != entry.logical_record_count
                or row["config_fingerprint"] != config_fingerprint
                or row["implementation_fingerprint"] != implementation_fingerprint
            ):
                raise RuntimeError(
                    "Resumed run source population, configuration, or implementation changed"
                )

    def rows(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM file_state ORDER BY relative_path COLLATE BINARY"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, relative_path: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM file_state WHERE relative_path = ?", (relative_path,)
        ).fetchone()
        if row is None:
            raise KeyError(relative_path)
        return dict(row)

    def mark_writing(
        self, relative_path: str, temporary_path: str, final_path: str
    ) -> int:
        now = _utc_now()
        with self.connection:
            row = self.connection.execute(
                "SELECT attempt FROM file_state WHERE relative_path = ?",
                (relative_path,),
            ).fetchone()
            if row is None:
                raise KeyError(relative_path)
            attempt = int(row["attempt"]) + 1
            self.connection.execute(
                """
                UPDATE file_state SET attempt=?, status='WRITING', temporary_path=?,
                    final_path=?, failure_code='', failure_detail='', started_at_utc=?,
                    updated_at_utc=?, completed_at_utc=''
                WHERE relative_path=?
                """,
                (attempt, temporary_path, final_path, now, now, relative_path),
            )
            self.connection.execute(
                """
                INSERT INTO attempt_history(
                    relative_path, attempt, started_at_utc, temporary_path
                ) VALUES (?, ?, ?, ?)
                """,
                (relative_path, attempt, now, temporary_path),
            )
        return attempt

    def mark_validating(self, relative_path: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE file_state SET status='VALIDATING', updated_at_utc=? WHERE relative_path=?",
                (_utc_now(), relative_path),
            )

    def mark_complete(self, relative_path: str, result: dict[str, Any]) -> None:
        now = _utc_now()
        validation_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
        with self.connection:
            row = self.connection.execute(
                "SELECT attempt FROM file_state WHERE relative_path=?", (relative_path,)
            ).fetchone()
            if row is None:
                raise KeyError(relative_path)
            self.connection.execute(
                """
                UPDATE file_state SET status='COMPLETE', source_semantic_digest=?,
                    staging_semantic_digest=?, output_sha256=?, output_size_bytes=?,
                    source_rows=?, staging_rows=?, validation_json=?, failure_code='',
                    failure_detail='', updated_at_utc=?, completed_at_utc=?
                WHERE relative_path=?
                """,
                (
                    result["source_semantic_digest"],
                    result["staging_semantic_digest"],
                    result["output_sha256"],
                    result["output_size_bytes"],
                    result["source_rows"],
                    result["staging_rows"],
                    validation_json,
                    now,
                    now,
                    relative_path,
                ),
            )
            self.connection.execute(
                """
                UPDATE attempt_history SET completed_at_utc=?, terminal_status='COMPLETE',
                    output_sha256=? WHERE relative_path=? AND attempt=?
                """,
                (now, result["output_sha256"], relative_path, int(row["attempt"])),
            )

    def mark_failed(self, relative_path: str, code: str, detail: str) -> None:
        now = _utc_now()
        safe_detail = detail[:500]
        with self.connection:
            row = self.connection.execute(
                "SELECT attempt FROM file_state WHERE relative_path=?", (relative_path,)
            ).fetchone()
            if row is None:
                raise KeyError(relative_path)
            self.connection.execute(
                """
                UPDATE file_state SET status='FAILED', failure_code=?, failure_detail=?,
                    updated_at_utc=?, completed_at_utc=? WHERE relative_path=?
                """,
                (code, safe_detail, now, now, relative_path),
            )
            self.connection.execute(
                """
                UPDATE attempt_history SET completed_at_utc=?, terminal_status='FAILED',
                    failure_code=? WHERE relative_path=? AND attempt=?
                """,
                (now, code, relative_path, int(row["attempt"])),
            )

    def integrity_check(self) -> str:
        return str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])

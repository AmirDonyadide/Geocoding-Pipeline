from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import FileResult, IdObservation, SourceFile
from .profiling import sha256_text


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS run_meta (
    key TEXT COLLATE BINARY PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS file_state (
    file_id INTEGER PRIMARY KEY,
    relative_path TEXT COLLATE BINARY NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'SCANNING', 'COMPLETE', 'FAILED')),
    size_bytes INTEGER,
    mtime_ns INTEGER,
    sha256 TEXT,
    result_json TEXT,
    anomaly_spool_name TEXT,
    error_code TEXT
);

CREATE TABLE IF NOT EXISTS unique_ids (
    id_value TEXT COLLATE BINARY PRIMARY KEY,
    id_sha256 TEXT NOT NULL,
    first_file_id INTEGER NOT NULL,
    first_logical_record_number INTEGER NOT NULL,
    last_file_id INTEGER NOT NULL,
    last_file_occurrence_count INTEGER NOT NULL,
    occurrence_count INTEGER NOT NULL,
    file_count INTEGER NOT NULL,
    has_within_file_duplicate INTEGER NOT NULL CHECK (has_within_file_duplicate IN (0, 1)),
    has_cross_file_duplicate INTEGER NOT NULL CHECK (has_cross_file_duplicate IN (0, 1))
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS duplicate_occurrences (
    id_value TEXT COLLATE BINARY NOT NULL,
    file_id INTEGER NOT NULL,
    logical_record_number INTEGER NOT NULL,
    is_first_occurrence INTEGER NOT NULL CHECK (is_first_occurrence IN (0, 1)),
    PRIMARY KEY (id_value, file_id, logical_record_number),
    FOREIGN KEY (id_value) REFERENCES unique_ids(id_value)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS duplicate_occurrences_file_idx
ON duplicate_occurrences(file_id, logical_record_number);
"""


@dataclass(frozen=True, slots=True)
class IdAddResult:
    distinct_in_file: bool
    first_within_file_duplicate: bool


class IdStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()
        self._harden_database_files()
        self._file_transaction_active = False

    def _harden_database_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                if candidate.is_symlink() or not candidate.is_file():
                    raise OSError("Phase 1 SQLite state is not a regular file")
                candidate.chmod(0o600)

    def close(self) -> None:
        if self._file_transaction_active:
            self.connection.rollback()
            self._file_transaction_active = False
        self._harden_database_files()
        self.connection.close()
        self._harden_database_files()

    def __enter__(self) -> "IdStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def set_meta(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO run_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.connection.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM run_meta WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])

    def prepare_files(self, files: list[SourceFile]) -> None:
        existing = self.connection.execute(
            "SELECT file_id, relative_path FROM file_state ORDER BY file_id"
        ).fetchall()
        expected = [(item.file_id, item.relative_path) for item in files]
        if existing and existing != expected:
            raise RuntimeError(
                "Discovered source file identity differs from the existing run; "
                "resume is unsafe"
            )
        if not existing:
            self.connection.executemany(
                "INSERT INTO file_state(file_id, relative_path, status) VALUES (?, ?, 'PENDING')",
                expected,
            )
            self.connection.commit()

    def file_states(self) -> dict[int, dict[str, object]]:
        rows = self.connection.execute(
            "SELECT file_id, relative_path, status, size_bytes, mtime_ns, sha256, "
            "result_json, anomaly_spool_name, error_code FROM file_state ORDER BY file_id"
        ).fetchall()
        columns = (
            "file_id",
            "relative_path",
            "status",
            "size_bytes",
            "mtime_ns",
            "sha256",
            "result_json",
            "anomaly_spool_name",
            "error_code",
        )
        return {int(row[0]): dict(zip(columns, row, strict=True)) for row in rows}

    def mark_scanning(self, source: SourceFile, size_bytes: int, mtime_ns: int) -> None:
        self.connection.execute(
            "UPDATE file_state SET status='SCANNING', size_bytes=?, mtime_ns=?, "
            "sha256=NULL, result_json=NULL, anomaly_spool_name=NULL, error_code=NULL "
            "WHERE file_id=? AND relative_path=?",
            (size_bytes, mtime_ns, source.file_id, source.relative_path),
        )
        self.connection.commit()

    def begin_file(self) -> None:
        if self._file_transaction_active:
            raise RuntimeError("A file transaction is already active")
        self.connection.execute("BEGIN IMMEDIATE")
        self._file_transaction_active = True

    def commit_file(self) -> None:
        if not self._file_transaction_active:
            raise RuntimeError("No file transaction is active")
        self.connection.commit()
        self._file_transaction_active = False

    def commit_file_result(
        self, result: FileResult, *, anomaly_spool_name: str
    ) -> None:
        """Atomically commit ID state and the file's COMPLETE checkpoint."""
        if not self._file_transaction_active:
            raise RuntimeError("No file transaction is active")
        self._update_file_result(
            result,
            status="COMPLETE",
            anomaly_spool_name=anomaly_spool_name,
        )
        self.connection.commit()
        self._file_transaction_active = False

    def rollback_file(self) -> None:
        if self._file_transaction_active:
            self.connection.rollback()
            self._file_transaction_active = False

    def add_ids(self, observations: Iterable[IdObservation]) -> list[IdAddResult]:
        if not self._file_transaction_active:
            raise RuntimeError("ID observations require an active file transaction")
        return [self._add_id(observation) for observation in observations]

    def _add_id(self, observation: IdObservation) -> IdAddResult:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO unique_ids("
            "id_value, id_sha256, first_file_id, first_logical_record_number, "
            "last_file_id, last_file_occurrence_count, occurrence_count, file_count, "
            "has_within_file_duplicate, has_cross_file_duplicate"
            ") VALUES (?, ?, ?, ?, ?, 1, 1, 1, 0, 0)",
            (
                observation.id_value,
                sha256_text(observation.id_value),
                observation.file_id,
                observation.logical_record_number,
                observation.file_id,
            ),
        )
        if cursor.rowcount == 1:
            return IdAddResult(distinct_in_file=True, first_within_file_duplicate=False)

        row = self.connection.execute(
            "SELECT first_file_id, first_logical_record_number, last_file_id, "
            "last_file_occurrence_count, occurrence_count, file_count, "
            "has_within_file_duplicate, has_cross_file_duplicate "
            "FROM unique_ids WHERE id_value = ? COLLATE BINARY",
            (observation.id_value,),
        ).fetchone()
        if row is None:
            raise RuntimeError("ID disappeared after conflict")
        (
            first_file_id,
            first_record,
            last_file_id,
            last_file_occurrences,
            occurrence_count,
            file_count,
            has_within,
            has_cross,
        ) = row

        if occurrence_count == 1:
            self.connection.execute(
                "INSERT INTO duplicate_occurrences("
                "id_value, file_id, logical_record_number, is_first_occurrence"
                ") VALUES (?, ?, ?, 1)",
                (observation.id_value, first_file_id, first_record),
            )
        self.connection.execute(
            "INSERT INTO duplicate_occurrences("
            "id_value, file_id, logical_record_number, is_first_occurrence"
            ") VALUES (?, ?, ?, 0)",
            (
                observation.id_value,
                observation.file_id,
                observation.logical_record_number,
            ),
        )

        same_file = int(last_file_id) == observation.file_id
        new_last_count = int(last_file_occurrences) + 1 if same_file else 1
        self.connection.execute(
            "UPDATE unique_ids SET last_file_id=?, last_file_occurrence_count=?, "
            "occurrence_count=occurrence_count+1, file_count=file_count+?, "
            "has_within_file_duplicate=?, has_cross_file_duplicate=? "
            "WHERE id_value = ? COLLATE BINARY",
            (
                observation.file_id,
                new_last_count,
                0 if same_file else 1,
                1 if same_file or has_within else 0,
                1 if (not same_file) or has_cross else 0,
                observation.id_value,
            ),
        )
        return IdAddResult(
            distinct_in_file=not same_file,
            first_within_file_duplicate=same_file and int(last_file_occurrences) == 1,
        )

    def save_file_result(
        self,
        result: FileResult,
        *,
        status: str,
        anomaly_spool_name: str,
    ) -> None:
        if status not in {"COMPLETE", "FAILED"}:
            raise ValueError(f"Invalid terminal file status: {status}")
        self._update_file_result(
            result,
            status=status,
            anomaly_spool_name=anomaly_spool_name,
        )
        self.connection.commit()

    def _update_file_result(
        self,
        result: FileResult,
        *,
        status: str,
        anomaly_spool_name: str,
    ) -> None:
        self.connection.execute(
            "UPDATE file_state SET status=?, size_bytes=?, mtime_ns=?, sha256=?, "
            "result_json=?, anomaly_spool_name=?, error_code=? WHERE file_id=?",
            (
                status,
                result.after_hash.size_bytes,
                result.after_hash.mtime_ns,
                result.sha256,
                json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True),
                anomaly_spool_name,
                result.error_code,
                result.file_id,
            ),
        )

    def load_results(self) -> list[FileResult]:
        rows = self.connection.execute(
            "SELECT result_json FROM file_state WHERE result_json IS NOT NULL ORDER BY file_id"
        ).fetchall()
        return [FileResult.from_dict(json.loads(row[0])) for row in rows]

    def duplicate_occurrence_rows(self) -> Iterable[tuple[object, ...]]:
        return self.connection.execute(
            "SELECT u.id_sha256, u.occurrence_count, u.file_count, "
            "CASE WHEN u.has_within_file_duplicate=1 AND u.has_cross_file_duplicate=1 "
            "THEN 'BOTH' WHEN u.has_cross_file_duplicate=1 THEN 'CROSS_FILE' "
            "ELSE 'WITHIN_FILE' END AS duplicate_scope, "
            "d.file_id, f.relative_path, d.logical_record_number "
            "FROM duplicate_occurrences d "
            "JOIN unique_ids u ON u.id_value = d.id_value COLLATE BINARY "
            "JOIN file_state f ON f.file_id = d.file_id "
            "ORDER BY u.id_sha256, d.file_id, d.logical_record_number"
        )

    def duplicate_summary(self) -> dict[str, int]:
        row = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(occurrence_count), 0), "
            "COALESCE(SUM(occurrence_count - 1), 0) "
            "FROM unique_ids WHERE occurrence_count > 1"
        ).fetchone()
        assert row is not None
        return {
            "duplicate_groups": int(row[0]),
            "duplicate_group_occurrences": int(row[1]),
            "excess_duplicate_occurrences": int(row[2]),
        }

    def integrity_check(self) -> str:
        row = self.connection.execute("PRAGMA integrity_check").fetchone()
        return "" if row is None else str(row[0])

    def checkpoint(self) -> None:
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._harden_database_files()

    @property
    def total_disk_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                total += candidate.stat().st_size
        return total

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import pyarrow as pa
import pyarrow.parquet as pq

from .constants import MANUAL_REVIEW_REASON_CODES_VERSION
from .review_v2 import (
    ALL_REVIEW_LABEL_FIELDS,
    ASSIGNMENT_ROLE_VALUES,
    COMPONENT_LABEL_FIELDS,
    CONFLICT_LABEL_VALUES,
    ERROR_CONDITION_LABEL_FIELDS,
    ERROR_CONDITION_LABEL_VALUES,
    MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
    MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
    MAX_PROTECTED_NOTE_CHARACTERS,
    OVERALL_LABEL_VALUES,
    REVIEW_EXPORT_MANIFEST_VERSION,
    REVIEW_PROGRESS_SCHEMA_VERSION,
    manual_review_schema_v2,
    validate_completed_review_record_v2,
    validate_reviewer_id,
)

ASSIGNMENT_ROLES: Final = ASSIGNMENT_ROLE_VALUES
ASSIGNMENT_STATUSES: Final = ("PENDING", "IN_PROGRESS", "COMPLETE")
REVIEWER_ONE_ID: Final = "R01"
REVIEWER_TWO_ID: Final = "R02"
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def require_owner_only_file(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("review progress/output may not be a symbolic link")
    if not path.is_file():
        raise FileNotFoundError("review progress file is missing")
    if path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
        raise ValueError("review progress file and parent must be owner-only")


@dataclass(frozen=True, slots=True)
class ReviewAssignment:
    hashed_review_id: str
    reviewer_id: str
    review_round: int
    assignment_role: str
    is_independent_review: bool
    display_order: int

    def validate(self) -> None:
        validate_reviewer_id(self.reviewer_id)
        if self.assignment_role not in ASSIGNMENT_ROLES:
            raise ValueError("invalid review assignment role")
        if self.review_round != 1:
            raise ValueError("review-interface v1 supports review round 1 only")
        if (
            self.assignment_role == "INDEPENDENT_SECOND"
            and not self.is_independent_review
        ):
            raise ValueError("independent second assignment must retain designation")
        if self.display_order < 0:
            raise ValueError("display order must be non-negative")
        if not re.fullmatch(r"[0-9a-f]{64}", self.hashed_review_id):
            raise ValueError("invalid hashed review ID")


@dataclass(frozen=True, slots=True)
class ProgressBinding:
    pilot_version: str
    protected_context_path: str
    protected_context_sha256: str
    protected_context_size_bytes: int
    portable_v1_path: str
    portable_v1_sha256: str
    portable_v1_size_bytes: int
    reviewed_parser_commit: str
    interface_implementation_commit: str
    interface_implementation_fingerprint: str

    def validate(self) -> None:
        if not self.pilot_version:
            raise ValueError("pilot version must be non-empty")
        for value in (self.protected_context_path, self.portable_v1_path):
            if not value or "\0" in value:
                raise ValueError("review input artifact path is invalid")
        for value in (self.protected_context_sha256, self.portable_v1_sha256):
            if not _FINGERPRINT_RE.fullmatch(value):
                raise ValueError("input artifact SHA-256 is invalid")
        if self.protected_context_size_bytes < 1 or self.portable_v1_size_bytes < 1:
            raise ValueError("input artifact size must be positive")
        if not _COMMIT_RE.fullmatch(self.reviewed_parser_commit):
            raise ValueError(
                "reviewed parser commit must be 40 lowercase hex characters"
            )
        if not _COMMIT_RE.fullmatch(self.interface_implementation_commit):
            raise ValueError(
                "review-interface implementation commit must be 40 lowercase hex characters"
            )
        if not _FINGERPRINT_RE.fullmatch(self.interface_implementation_fingerprint):
            raise ValueError("review-interface fingerprint must be SHA-256")

    def metadata(self) -> dict[str, str]:
        self.validate()
        return {
            "pilot_version": self.pilot_version,
            "protected_context_path": self.protected_context_path,
            "protected_context_sha256": self.protected_context_sha256,
            "protected_context_size_bytes": str(self.protected_context_size_bytes),
            "portable_v1_path": self.portable_v1_path,
            "portable_v1_sha256": self.portable_v1_sha256,
            "portable_v1_size_bytes": str(self.portable_v1_size_bytes),
            "reviewed_parser_commit": self.reviewed_parser_commit,
            "interface_implementation_commit": self.interface_implementation_commit,
            "interface_implementation_fingerprint": (
                self.interface_implementation_fingerprint
            ),
            "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
            "label_vocabulary_version": MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
            "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
            "progress_schema_version": REVIEW_PROGRESS_SCHEMA_VERSION,
        }


def _label_check(field: str, values: Sequence[str]) -> str:
    allowed = ",".join(f"'{value}'" for value in values)
    return f"{field} TEXT CHECK ({field} IS NULL OR {field} IN ({allowed}))"


class ReviewProgressStore:
    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        self.path = path
        require_owner_only_file(path)
        if readonly:
            self.connection = sqlite3.connect(
                f"file:{path}?mode=ro", uri=True, isolation_level=None
            )
        else:
            self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        if not readonly:
            mode = self.connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if str(mode).lower() != "delete":
                raise RuntimeError(
                    "review progress requires SQLite DELETE journal mode"
                )
            self.connection.execute("PRAGMA synchronous=FULL")

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        binding: ProgressBinding,
        reviewer_id: str,
        reviewer_role: str,
        assignments: Sequence[ReviewAssignment],
        created_at_utc: str | None = None,
    ) -> ReviewProgressStore:
        if path.exists():
            raise FileExistsError("review progress database already exists")
        validate_reviewer_id(reviewer_id)
        if reviewer_role not in ASSIGNMENT_ROLES:
            raise ValueError("invalid reviewer role")
        if not assignments:
            raise ValueError("reviewer assignment set is empty")
        for assignment in assignments:
            assignment.validate()
            if assignment.reviewer_id != reviewer_id:
                raise ValueError("assignment reviewer does not match progress store")
            if assignment.assignment_role != reviewer_role:
                raise ValueError("assignment role does not match progress store")
        if len({item.hashed_review_id for item in assignments}) != len(assignments):
            raise ValueError("duplicate hashed review assignment")
        if len({item.display_order for item in assignments}) != len(assignments):
            raise ValueError("duplicate review display order")

        path.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
        path.parent.chmod(0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        path.chmod(0o600)
        store = cls(path)
        try:
            store._create_schema()
            metadata = {
                **binding.metadata(),
                "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_role,
                "expected_assignment_count": str(len(assignments)),
                "created_at_utc": created_at_utc or utc_now(),
            }
            store.connection.execute("BEGIN IMMEDIATE")
            try:
                store.connection.executemany(
                    "INSERT INTO run_metadata(key,value) VALUES(?,?)",
                    sorted(metadata.items()),
                )
                store.connection.executemany(
                    """
                    INSERT INTO assignment(
                        hashed_review_id,reviewer_id,review_round,assignment_role,
                        is_independent_review,display_order,status
                    ) VALUES(?,?,?,?,?,?, 'PENDING')
                    """,
                    [
                        (
                            item.hashed_review_id,
                            item.reviewer_id,
                            item.review_round,
                            item.assignment_role,
                            int(item.is_independent_review),
                            item.display_order,
                        )
                        for item in assignments
                    ],
                )
                timestamp = metadata["created_at_utc"]
                store.connection.executemany(
                    """
                    INSERT INTO review_label(
                        hashed_review_id,reviewer_id,review_round,
                        reason_codes_json,revision,created_at_utc,updated_at_utc
                    ) VALUES(?,?,?,'[]',0,?,?)
                    """,
                    [
                        (
                            item.hashed_review_id,
                            item.reviewer_id,
                            item.review_round,
                            timestamp,
                            timestamp,
                        )
                        for item in assignments
                    ],
                )
                first = min(item.display_order for item in assignments)
                store.connection.execute(
                    "INSERT INTO review_cursor(reviewer_id,current_display_order,updated_at_utc) VALUES(?,?,?)",
                    (reviewer_id, first, timestamp),
                )
                store.connection.commit()
            except Exception:
                store.connection.rollback()
                raise
            if store.integrity_check() != "ok":
                raise RuntimeError(
                    "new review progress database failed integrity check"
                )
            return store
        except Exception:
            store.close()
            if path.exists():
                path.unlink()
            path.parent.rmdir()
            raise

    def _create_schema(self) -> None:
        component_checks = ",\n".join(
            _label_check(
                field,
                ("CORRECT", "INCORRECT", "MISSED", "NOT_PRESENT", "CANNOT_ASSESS"),
            )
            for field in COMPONENT_LABEL_FIELDS
        )
        error_checks = ",\n".join(
            _label_check(field, ERROR_CONDITION_LABEL_VALUES)
            for field in ERROR_CONDITION_LABEL_FIELDS
        )
        self.connection.executescript(
            f"""
            CREATE TABLE run_metadata(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE assignment(
                hashed_review_id TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                review_round INTEGER NOT NULL CHECK(review_round=1),
                assignment_role TEXT NOT NULL CHECK(assignment_role IN ('PRIMARY','INDEPENDENT_SECOND')),
                is_independent_review INTEGER NOT NULL CHECK(is_independent_review IN (0,1)),
                display_order INTEGER NOT NULL UNIQUE CHECK(display_order>=0),
                status TEXT NOT NULL CHECK(status IN ('PENDING','IN_PROGRESS','COMPLETE')),
                PRIMARY KEY(hashed_review_id,reviewer_id,review_round)
            ) WITHOUT ROWID;
            CREATE TABLE review_label(
                hashed_review_id TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                review_round INTEGER NOT NULL,
                {component_checks},
                {_label_check("conflict_correctness_label", CONFLICT_LABEL_VALUES)},
                {error_checks},
                {_label_check("overall_parse_acceptability_label", OVERALL_LABEL_VALUES)},
                reason_codes_json TEXT NOT NULL DEFAULT '[]',
                protected_note TEXT CHECK(protected_note IS NULL OR length(protected_note)<={MAX_PROTECTED_NOTE_CHARACTERS}),
                revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY(hashed_review_id,reviewer_id,review_round),
                FOREIGN KEY(hashed_review_id,reviewer_id,review_round)
                    REFERENCES assignment(hashed_review_id,reviewer_id,review_round)
            ) WITHOUT ROWID;
            CREATE TABLE review_cursor(
                reviewer_id TEXT PRIMARY KEY,
                current_display_order INTEGER NOT NULL CHECK(current_display_order>=0),
                updated_at_utc TEXT NOT NULL
            ) WITHOUT ROWID;
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ReviewProgressStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def integrity_check(self) -> str:
        return str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])

    def metadata(self) -> dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in self.connection.execute("SELECT key,value FROM run_metadata")
        }

    def verify_binding(self, binding: ProgressBinding) -> None:
        expected = binding.metadata()
        observed = self.metadata()
        for key, value in expected.items():
            if observed.get(key) != value:
                raise ValueError("review progress input/version binding mismatch")
        if self.integrity_check() != "ok":
            raise ValueError("review progress SQLite integrity check failed")

    def reviewer_id(self) -> str:
        return self.metadata()["reviewer_id"]

    def assignment_count(self) -> int:
        return int(
            self.connection.execute("SELECT COUNT(*) FROM assignment").fetchone()[0]
        )

    def assignment_ids(self) -> tuple[str, ...]:
        return tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT hashed_review_id FROM assignment ORDER BY display_order"
            )
        )

    def assignment(self, hashed_review_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM assignment WHERE hashed_review_id=?",
            (hashed_review_id,),
        ).fetchone()
        if row is None:
            raise KeyError("review identity is not assigned to this reviewer")
        return dict(row)

    def assignment_at(self, display_order: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM assignment WHERE display_order=?", (display_order,)
        ).fetchone()
        return None if row is None else dict(row)

    def cursor(self) -> int:
        reviewer = self.reviewer_id()
        row = self.connection.execute(
            "SELECT current_display_order FROM review_cursor WHERE reviewer_id=?",
            (reviewer,),
        ).fetchone()
        if row is None:
            raise RuntimeError("review cursor is missing")
        return int(row[0])

    def _set_cursor(self, display_order: int, timestamp: str) -> None:
        self.connection.execute(
            "UPDATE review_cursor SET current_display_order=?,updated_at_utc=? WHERE reviewer_id=?",
            (display_order, timestamp, self.reviewer_id()),
        )

    def mark_in_progress(self, hashed_review_id: str) -> None:
        self.assignment(hashed_review_id)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "UPDATE assignment SET status='IN_PROGRESS' WHERE hashed_review_id=? AND status='PENDING'",
                (hashed_review_id,),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def label_values(self, hashed_review_id: str) -> dict[str, Any]:
        self.assignment(hashed_review_id)
        row = self.connection.execute(
            "SELECT * FROM review_label WHERE hashed_review_id=?",
            (hashed_review_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("review label row is missing")
        value = dict(row)
        value["reason_codes"] = json.loads(str(value.pop("reason_codes_json")))
        return value

    def save_completed(
        self,
        hashed_review_id: str,
        labels: Mapping[str, str],
        reason_codes: Sequence[str],
        *,
        protected_note: str | None,
        updated_at_utc: str | None = None,
    ) -> None:
        assignment = self.assignment(hashed_review_id)
        metadata = self.metadata()
        portable = {
            "hashed_review_id": hashed_review_id,
            "pilot_version": metadata["pilot_version"],
            "sample_partition": "DEVELOPMENT",
            "reviewer_id": assignment["reviewer_id"],
            "review_round": assignment["review_round"],
            "is_independent_review": bool(assignment["is_independent_review"]),
            "assignment_role": assignment["assignment_role"],
            **{field: labels.get(field) for field in ALL_REVIEW_LABEL_FIELDS},
            "reason_codes": list(reason_codes),
            "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
            "label_vocabulary_version": MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
            "adjudicated_label": None,
            "adjudicator_id": None,
            "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
        }
        canonical_reasons = validate_completed_review_record_v2(
            portable, protected_note=protected_note
        )
        timestamp = updated_at_utc or utc_now()
        next_row = self.connection.execute(
            """
            SELECT display_order FROM assignment
            WHERE display_order>? AND status!='COMPLETE'
            ORDER BY display_order LIMIT 1
            """,
            (assignment["display_order"],),
        ).fetchone()
        next_order = int(next_row[0]) if next_row else int(assignment["display_order"])
        values = [labels[field] for field in ALL_REVIEW_LABEL_FIELDS]
        set_clause = ",".join(f"{field}=?" for field in ALL_REVIEW_LABEL_FIELDS)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                f"""
                UPDATE review_label SET {set_clause},reason_codes_json=?,protected_note=?,
                    revision=revision+1,updated_at_utc=?
                WHERE hashed_review_id=? AND reviewer_id=? AND review_round=?
                """,
                (
                    *values,
                    json.dumps(list(canonical_reasons), separators=(",", ":")),
                    protected_note,
                    timestamp,
                    hashed_review_id,
                    assignment["reviewer_id"],
                    assignment["review_round"],
                ),
            )
            self.connection.execute(
                "UPDATE assignment SET status='COMPLETE' WHERE hashed_review_id=?",
                (hashed_review_id,),
            )
            self._set_cursor(next_order, timestamp)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def move_cursor(
        self, display_order: int, *, updated_at_utc: str | None = None
    ) -> None:
        if self.assignment_at(display_order) is None:
            raise ValueError("cursor target is outside reviewer assignments")
        timestamp = updated_at_utc or utc_now()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._set_cursor(display_order, timestamp)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def next_incomplete(self, *, after: int = -1) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM assignment WHERE display_order>? AND status!='COMPLETE'
            ORDER BY display_order LIMIT 1
            """,
            (after,),
        ).fetchone()
        if row is None and after >= 0:
            row = self.connection.execute(
                "SELECT * FROM assignment WHERE status!='COMPLETE' ORDER BY display_order LIMIT 1"
            ).fetchone()
        return None if row is None else dict(row)

    def summary(self) -> dict[str, Any]:
        counts = {
            str(row[0]): int(row[1])
            for row in self.connection.execute(
                "SELECT status,COUNT(*) FROM assignment GROUP BY status"
            )
        }
        total = self.assignment_count()
        notes = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM review_label WHERE protected_note IS NOT NULL"
            ).fetchone()[0]
        )
        return {
            "reviewer_id": self.reviewer_id(),
            "reviewer_role": self.metadata()["reviewer_role"],
            "assignment_count": total,
            "pending_count": counts.get("PENDING", 0),
            "in_progress_count": counts.get("IN_PROGRESS", 0),
            "complete_count": counts.get("COMPLETE", 0),
            "remaining_count": total - counts.get("COMPLETE", 0),
            "protected_note_count": notes,
            "raw_values_in_summary": False,
        }

    def completed_portable_rows(self) -> list[dict[str, Any]]:
        if self.summary()["remaining_count"] != 0:
            raise ValueError("reviewer assignments are incomplete")
        metadata = self.metadata()
        rows = self.connection.execute(
            """
            SELECT a.*,l.* FROM assignment a
            JOIN review_label l USING(hashed_review_id,reviewer_id,review_round)
            ORDER BY a.hashed_review_id,a.reviewer_id,a.review_round
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            portable = {
                "hashed_review_id": row["hashed_review_id"],
                "pilot_version": metadata["pilot_version"],
                "sample_partition": "DEVELOPMENT",
                "reviewer_id": row["reviewer_id"],
                "review_round": row["review_round"],
                "is_independent_review": bool(row["is_independent_review"]),
                "assignment_role": row["assignment_role"],
                **{field: row[field] for field in ALL_REVIEW_LABEL_FIELDS},
                "reason_codes": json.loads(str(row["reason_codes_json"])),
                "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
                "label_vocabulary_version": MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
                "adjudicated_label": None,
                "adjudicator_id": None,
                "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
            }
            validate_completed_review_record_v2(
                portable, protected_note=row["protected_note"]
            )
            result.append(portable)
        return result


def _matching_bindings(first: Mapping[str, str], second: Mapping[str, str]) -> None:
    keys = (
        "pilot_version",
        "protected_context_path",
        "protected_context_sha256",
        "protected_context_size_bytes",
        "portable_v1_path",
        "portable_v1_sha256",
        "portable_v1_size_bytes",
        "reviewed_parser_commit",
        "interface_implementation_commit",
        "interface_implementation_fingerprint",
        "label_schema_version",
        "label_vocabulary_version",
        "reason_codes_version",
        "progress_schema_version",
    )
    if any(first.get(key) != second.get(key) for key in keys):
        raise ValueError("reviewer progress stores have different bindings")


def _sanitized_manifest_artifact(
    *, artifact_id: str, bound_path: str, sha256: str, size_bytes: int
) -> dict[str, Any]:
    """Return portable artifact identity without machine-specific path material."""
    result: dict[str, Any] = {
        "artifact_id": artifact_id,
        "sha256": sha256,
        "size_bytes": size_bytes,
    }
    path = Path(bound_path)
    if not path.is_absolute():
        normalized = Path(os.path.normpath(bound_path))
        if ".." not in normalized.parts and normalized.parts[:3] == (
            "derived",
            "controlled",
            "phase03_v1",
        ):
            result["repository_relative_path"] = normalized.as_posix()
    return result


def export_completed_reviews(
    reviewer_one_database: Path,
    reviewer_two_database: Path,
    output_directory: Path,
    *,
    export_timestamp_utc: str | None = None,
    expected_reviewer_one_records: int = 800,
    expected_reviewer_two_records: int = 200,
) -> tuple[Path, Path]:
    if output_directory.exists():
        raise FileExistsError("review export directory already exists")
    temporary_directory = output_directory.with_name(
        f".{output_directory.name}.export.{os.getpid()}"
    )
    if temporary_directory.exists():
        raise FileExistsError("review export temporary directory already exists")
    require_owner_only_file(reviewer_one_database)
    require_owner_only_file(reviewer_two_database)
    with (
        ReviewProgressStore(reviewer_one_database, readonly=True) as first,
        ReviewProgressStore(reviewer_two_database, readonly=True) as second,
    ):
        first_metadata = first.metadata()
        second_metadata = second.metadata()
        _matching_bindings(first_metadata, second_metadata)
        if (
            first_metadata["interface_implementation_fingerprint"]
            != current_interface_fingerprint()
        ):
            raise ValueError("review-interface implementation fingerprint changed")
        if (
            first_metadata["interface_implementation_commit"]
            != current_repository_commit()
        ):
            raise ValueError("review-interface implementation commit changed")
        if (
            first_metadata["reviewer_id"] != REVIEWER_ONE_ID
            or first_metadata["reviewer_role"] != "PRIMARY"
        ):
            raise ValueError("Reviewer 1 progress store identity/role mismatch")
        if (
            second_metadata["reviewer_id"] != REVIEWER_TWO_ID
            or second_metadata["reviewer_role"] != "INDEPENDENT_SECOND"
        ):
            raise ValueError("Reviewer 2 progress store identity/role mismatch")
        first_rows = first.completed_portable_rows()
        second_rows = second.completed_portable_rows()
        if len(first_rows) != expected_reviewer_one_records:
            raise ValueError("Reviewer 1 completed record count mismatch")
        if len(second_rows) != expected_reviewer_two_records:
            raise ValueError("Reviewer 2 completed record count mismatch")
        designated = {
            str(row["hashed_review_id"])
            for row in first_rows
            if row["is_independent_review"] is True
        }
        second_ids = {str(row["hashed_review_id"]) for row in second_rows}
        if len(designated) != expected_reviewer_two_records or second_ids != designated:
            raise ValueError("independent double-review designation mismatch")
        if not all(row["is_independent_review"] is True for row in second_rows):
            raise ValueError("Reviewer 2 record lost independent designation")
        records = sorted(
            [*first_rows, *second_rows],
            key=lambda row: (
                str(row["hashed_review_id"]),
                str(row["reviewer_id"]).encode("utf-8"),
                int(row["review_round"]),
            ),
        )
        composite_keys = {
            (row["hashed_review_id"], row["reviewer_id"], row["review_round"])
            for row in records
        }
        if len(composite_keys) != len(records):
            raise ValueError("duplicate portable reviewer composite key")

        temporary_directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        temporary_directory.chmod(0o700)
        parquet_path = temporary_directory / "portable_review_labels_v2.parquet"
        manifest_path = temporary_directory / "portable_review_export_manifest.json"
        temporary_parquet = (
            temporary_directory / ".portable_review_labels_v2.parquet.tmp"
        )
        temporary_manifest = (
            temporary_directory / ".portable_review_export_manifest.json.tmp"
        )
        try:
            table = pa.Table.from_pylist(records, schema=manual_review_schema_v2())
            pq.write_table(
                table,
                temporary_parquet,
                compression="zstd",
                compression_level=3,
                write_statistics=False,
                write_page_checksum=True,
            )
            temporary_parquet.chmod(0o600)
            verified = pq.ParquetFile(
                temporary_parquet,
                page_checksum_verification=True,
                pre_buffer=True,
            )
            if (
                verified.metadata.num_rows != len(records)
                or verified.schema_arrow.remove_metadata()
                != manual_review_schema_v2().remove_metadata()
            ):
                raise ValueError("portable v2 Parquet read-back validation failed")
            if verified.read(use_threads=False).to_pylist() != records:
                raise ValueError("portable v2 values changed during Parquet write")
            parquet_sha256 = file_sha256(temporary_parquet)
            timestamp = export_timestamp_utc or utc_now()
            manifest = {
                "manifest_version": REVIEW_EXPORT_MANIFEST_VERSION,
                "input_artifacts": {
                    "protected_review_context": _sanitized_manifest_artifact(
                        artifact_id="phase03_protected_review_context",
                        bound_path=first_metadata["protected_context_path"],
                        sha256=first_metadata["protected_context_sha256"],
                        size_bytes=int(first_metadata["protected_context_size_bytes"]),
                    ),
                    "portable_review_labels_v1": _sanitized_manifest_artifact(
                        artifact_id="phase03_portable_review_labels_v1",
                        bound_path=first_metadata["portable_v1_path"],
                        sha256=first_metadata["portable_v1_sha256"],
                        size_bytes=int(first_metadata["portable_v1_size_bytes"]),
                    ),
                },
                "reviewed_parser_commit": first_metadata["reviewed_parser_commit"],
                "review_interface_implementation_commit": first_metadata[
                    "interface_implementation_commit"
                ],
                "review_interface_implementation_fingerprint": first_metadata[
                    "interface_implementation_fingerprint"
                ],
                "schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
                "label_vocabulary_version": MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
                "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
                "reviewer_1_record_count": len(first_rows),
                "reviewer_2_record_count": len(second_rows),
                "total_reviewer_record_count": len(records),
                "exported_at_utc": timestamp,
                "portable_parquet_sha256": parquet_sha256,
                "portable_parquet_size_bytes": temporary_parquet.stat().st_size,
                "protected_or_raw_values_in_manifest": False,
            }
            temporary_manifest.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            temporary_manifest.chmod(0o600)
            os.replace(temporary_parquet, parquet_path)
            os.replace(temporary_manifest, manifest_path)
            parquet_path.chmod(0o600)
            manifest_path.chmod(0o600)
            _fsync_parent(parquet_path)
            os.replace(temporary_directory, output_directory)
            output_directory.chmod(0o700)
            _fsync_parent(output_directory)
            return (
                output_directory / parquet_path.name,
                output_directory / manifest_path.name,
            )
        except Exception:
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory)
            raise


def interface_source_fingerprint(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(b"safe_geocoding_pipeline:phase03_review_interface_v1\0")
    for path in sorted(paths, key=lambda item: item.name.encode("utf-8")):
        digest.update(len(path.name.encode()).to_bytes(8, "big"))
        digest.update(path.name.encode())
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def current_interface_fingerprint() -> str:
    root = Path(__file__).resolve().parent
    return interface_source_fingerprint(
        root / name
        for name in (
            "review_v2.py",
            "review_progress.py",
            "review_interface.py",
            "review_cli.py",
        )
    )


def current_repository_commit() -> str:
    repository_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not _COMMIT_RE.fullmatch(commit):
        raise RuntimeError("review-interface Git commit identity is invalid")
    return commit

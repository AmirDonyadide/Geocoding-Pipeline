from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s00_models import (
    FileResult,
    IdObservation,
    SourceFile,
)
from safe_geocoding_pipeline.preprocessing.stages.s00_profiling import sha256_text
from safe_geocoding_pipeline.preprocessing.stages.s00_store import IdStore


def test_store_rejects_sqlite_symlink_before_opening_it(tmp_path: Path) -> None:
    target = tmp_path / "outside.sqlite3"
    original = b"fictional external content"
    target.write_bytes(original)
    link = tmp_path / "ids.sqlite3"
    link.symlink_to(target)

    with pytest.raises(OSError, match="not a regular file"):
        IdStore(link)
    assert target.read_bytes() == original


def test_store_metadata_cannot_be_reinterpreted_on_resume(tmp_path: Path) -> None:
    with IdStore(tmp_path / "ids.sqlite3") as store:
        store.set_meta("population_scope_sha256", "a" * 64)
        store.set_meta("population_scope_sha256", "a" * 64)
        with pytest.raises(RuntimeError, match="population_scope_sha256"):
            store.set_meta("population_scope_sha256", "b" * 64)
        assert store.get_meta("population_scope_sha256") == "a" * 64


def test_compact_store_tracks_within_and_cross_file_duplicates(tmp_path: Path) -> None:
    database = tmp_path / "ids.sqlite3"
    files = [
        SourceFile(1, tmp_path / "a.csv", "a.csv", "a.csv"),
        SourceFile(2, tmp_path / "b.csv", "b.csv", "b.csv"),
    ]
    with IdStore(database) as store:
        store.prepare_files(files)
        store.begin_file()
        first_batch = store.add_ids(
            [
                IdObservation("001", 1, 1),
                IdObservation("001", 1, 2),
                IdObservation("002", 1, 3),
            ]
        )
        store.commit_file()
        assert [item.distinct_in_file for item in first_batch] == [True, False, True]
        assert first_batch[1].first_within_file_duplicate is True

        store.begin_file()
        second_batch = store.add_ids(
            [IdObservation("001", 2, 1), IdObservation("001", 2, 2)]
        )
        store.commit_file()
        assert [item.distinct_in_file for item in second_batch] == [True, False]
        assert second_batch[1].first_within_file_duplicate is True

        rows = list(store.duplicate_occurrence_rows())
        assert len(rows) == 4
        assert {row[0] for row in rows} == {sha256_text("001")}
        assert {row[3] for row in rows} == {"BOTH"}
        assert store.duplicate_summary() == {
            "duplicate_groups": 1,
            "duplicate_group_occurrences": 4,
            "excess_duplicate_occurrences": 3,
        }


def test_failed_file_transaction_rolls_back_all_id_state(tmp_path: Path) -> None:
    database = tmp_path / "ids.sqlite3"
    with IdStore(database) as store:
        store.begin_file()
        store.add_ids([IdObservation("rollback-me", 1, 1)])
        store.rollback_file()
        count = store.connection.execute("SELECT COUNT(*) FROM unique_ids").fetchone()[
            0
        ]
        assert count == 0


def test_sqlite_uses_binary_text_and_only_duplicate_occurrences(tmp_path: Path) -> None:
    database = tmp_path / "ids.sqlite3"
    with IdStore(database) as store:
        store.begin_file()
        store.add_ids(
            [
                IdObservation("01", 1, 1),
                IdObservation("1", 1, 2),
                IdObservation("Case", 1, 3),
                IdObservation("case", 1, 4),
            ]
        )
        store.commit_file()
        assert (
            store.connection.execute("SELECT COUNT(*) FROM unique_ids").fetchone()[0]
            == 4
        )
        assert (
            store.connection.execute(
                "SELECT COUNT(*) FROM duplicate_occurrences"
            ).fetchone()[0]
            == 0
        )

    connection = sqlite3.connect(database)
    sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name='unique_ids'"
    ).fetchone()[0]
    assert "COLLATE BINARY" in sql
    connection.close()


def test_scanning_state_survives_interruption_without_uncommitted_ids(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ids.sqlite3"
    source = SourceFile(1, tmp_path / "a.csv", "a.csv", "a.csv")
    store = IdStore(database)
    store.prepare_files([source])
    store.mark_scanning(source, 10, 20)
    store.begin_file()
    store.add_ids([IdObservation("interrupted", 1, 1)])
    store.close()

    with IdStore(database) as reopened:
        assert reopened.file_states()[1]["status"] == "SCANNING"
        assert (
            reopened.connection.execute("SELECT COUNT(*) FROM unique_ids").fetchone()[0]
            == 0
        )


def test_complete_checkpoint_and_ids_commit_atomically(tmp_path: Path) -> None:
    database = tmp_path / "ids.sqlite3"
    source = SourceFile(1, tmp_path / "a.csv", "a.csv", "a.csv")
    with IdStore(database) as store:
        store.prepare_files([source])
        store.mark_scanning(source, 10, 20)
        store.begin_file()
        store.add_ids([IdObservation("committed", 1, 1)])
        result = FileResult(1, "a.csv", "a.csv", scan_status="COMPLETE")
        store.commit_file_result(result, anomaly_spool_name="file_000001.csv")
        assert store.file_states()[1]["status"] == "COMPLETE"
        assert (
            store.connection.execute("SELECT COUNT(*) FROM unique_ids").fetchone()[0]
            == 1
        )

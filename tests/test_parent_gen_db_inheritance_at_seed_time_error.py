"""Error-path tests for bob3.parent_gen_db_inheritance.

Verifies that invalid input raises ValueError and functions do not silently
succeed.
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.parent_gen_db_inheritance import read_parent_features, stamp_child_row


_SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj-1',
    spec_slot TEXT,
    status TEXT DEFAULT 'pending',
    updated_at TEXT,
    parent_status TEXT,
    parent_completed_at TEXT,
    parent_evidence_hash TEXT
);
CREATE TABLE IF NOT EXISTS evidence_artifacts (
    id TEXT PRIMARY KEY,
    feature_id TEXT,
    content TEXT,
    is_current INTEGER DEFAULT 1,
    created_at TEXT
);
"""


def _init_db(path: pathlib.Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _insert_feature(
    path: pathlib.Path,
    *,
    spec_slot: str | None = "F-R7-001",
    status: str = "pending",
) -> str:
    fid = str(uuid.uuid4())
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO features (id, project_id, spec_slot, status, updated_at) VALUES (?,?,?,?,?)",
        (fid, "proj-1", spec_slot, status, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return fid


class TestReadParentFeaturesErrors:
    def test_none_path_raises_value_error(self):
        with pytest.raises(ValueError, match="None"):
            read_parent_features(None)

    def test_empty_string_path_raises_value_error(self):
        with pytest.raises(ValueError):
            read_parent_features("")

    def test_missing_db_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_parent_features(tmp_path / "does_not_exist.db")

    def test_does_not_silently_succeed_on_none(self):
        """Confirm None never produces an empty dict — it must raise."""
        with pytest.raises((ValueError, TypeError)):
            result = read_parent_features(None)
            # If no exception was raised, this assertion forces the test to fail
            assert False, f"Expected exception but got: {result}"


class TestStampChildRowErrors:
    def test_none_feature_id_raises_value_error(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        with pytest.raises((ValueError, TypeError)):
            stamp_child_row(
                child_db_path=db,
                feature_id=None,
                parent_status="completed",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        with pytest.raises(ValueError):
            stamp_child_row(
                child_db_path=db,
                feature_id="",
                parent_status="completed",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )

    def test_none_parent_status_raises_value_error(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db)
        with pytest.raises((ValueError, TypeError)):
            stamp_child_row(
                child_db_path=db,
                feature_id=fid,
                parent_status=None,
                parent_completed_at=None,
                parent_evidence_hash=None,
            )

    def test_empty_parent_status_raises_value_error(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db)
        with pytest.raises(ValueError):
            stamp_child_row(
                child_db_path=db,
                feature_id=fid,
                parent_status="",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )

    def test_missing_child_db_raises_file_not_found(self, tmp_path):
        fid = str(uuid.uuid4())
        with pytest.raises(FileNotFoundError):
            stamp_child_row(
                child_db_path=tmp_path / "nonexistent.db",
                feature_id=fid,
                parent_status="completed",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )

    def test_does_not_silently_succeed_on_empty_status(self, tmp_path):
        """Confirm empty parent_status never silently updates the DB."""
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db)

        raised = False
        try:
            stamp_child_row(
                child_db_path=db,
                feature_id=fid,
                parent_status="",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )
        except ValueError:
            raised = True

        assert raised, "stamp_child_row with empty parent_status must raise ValueError"

        # Confirm nothing was written
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT parent_status FROM features WHERE id=?", (fid,)).fetchone()
        conn.close()
        assert row[0] is None, "parent_status must not be written when ValueError is raised"

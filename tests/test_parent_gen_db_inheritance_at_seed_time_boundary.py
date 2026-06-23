"""Boundary tests for bob3.parent_gen_db_inheritance.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising.
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
    spec_slot: str | None,
    status: str = "completed",
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


class TestReadParentFeaturesBoundary:
    def test_empty_db_returns_empty_dict(self, tmp_path):
        """An empty features table returns {} rather than raising."""
        db = tmp_path / "parent.db"
        _init_db(db)
        result = read_parent_features(db)
        assert result == {}

    def test_single_completed_row_minimum_case(self, tmp_path):
        """Single qualifying row — minimum valid result."""
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-001", status="completed")
        result = read_parent_features(db)
        assert len(result) == 1
        assert result["F-R7-001"].id == fid

    def test_all_pending_rows_returns_empty_dict(self, tmp_path):
        """All rows pending — no qualifying rows, returns {}."""
        db = tmp_path / "parent.db"
        _init_db(db)
        for i in range(3):
            _insert_feature(db, spec_slot=f"F-R7-{i:03d}", status="pending")
        result = read_parent_features(db)
        assert result == {}

    def test_null_spec_slot_rows_excluded(self, tmp_path):
        """Rows with NULL spec_slot are excluded; result is empty, not an error."""
        db = tmp_path / "parent.db"
        _init_db(db)
        for _ in range(3):
            _insert_feature(db, spec_slot=None, status="completed")
        result = read_parent_features(db)
        assert result == {}

    def test_duplicate_slot_last_write_wins(self, tmp_path):
        """If multiple rows share a spec_slot, result contains exactly one entry."""
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-999", status="completed")
        _insert_feature(db, spec_slot="F-R7-999", status="needs_human")
        result = read_parent_features(db)
        # Must have exactly one entry, not raise
        assert len(result) == 1
        assert "F-R7-999" in result


class TestStampChildRowBoundary:
    def test_stamp_with_none_parent_completed_at(self, tmp_path):
        """None parent_completed_at is written without raising."""
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-001", status="pending")
        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT parent_status FROM features WHERE id=?", (fid,)).fetchone()
        conn.close()
        assert row[0] == "completed"

    def test_stamp_with_none_evidence_hash(self, tmp_path):
        """None parent_evidence_hash is written without raising."""
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-002", status="pending")
        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="needs_human",
            parent_completed_at="2026-01-01T00:00:00",
            parent_evidence_hash=None,
        )
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT parent_evidence_hash FROM features WHERE id=?", (fid,)
        ).fetchone()
        conn.close()
        assert row[0] is None

    def test_stamp_unknown_feature_id_is_a_no_op(self, tmp_path):
        """Stamping a nonexistent feature_id does not raise — UPDATE simply matches 0 rows."""
        db = tmp_path / "child.db"
        _init_db(db)
        fake_id = str(uuid.uuid4())
        stamp_child_row(
            child_db_path=db,
            feature_id=fake_id,
            parent_status="completed",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )
        # No exception raised — that is the contract

    def test_stamp_needs_human_status(self, tmp_path):
        """needs_human is a valid parent_status value."""
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-003", status="pending")
        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="needs_human",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT parent_status FROM features WHERE id=?", (fid,)).fetchone()
        conn.close()
        assert row[0] == "needs_human"

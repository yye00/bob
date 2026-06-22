"""Tests for bob3.parent_inheritance.inherit_parent_status (F-R7-400)."""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.parent_inheritance import inherit_parent_status, InheritParentStatusResult


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


def _read_feature(path: pathlib.Path, feature_id: str) -> dict:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM features WHERE id=?", (feature_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


class TestInheritParentStatus:
    def test_returns_named_tuple_result(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)
        assert isinstance(result, InheritParentStatusResult)

    def test_stamps_matching_completed_row(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(parent_db, spec_slot="F-R7-400", status="completed")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        assert result.skipped_no_slot == 0
        assert result.skipped_no_parent_match == 0

        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_status"] == "completed"

    def test_stamps_needs_human_status(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(parent_db, spec_slot="F-R7-400", status="needs_human")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_status"] == "needs_human"

    def test_stamps_regression_status(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(parent_db, spec_slot="F-R7-400", status="regression")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_status"] == "regression"

    def test_pending_parent_rows_not_stamped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(parent_db, spec_slot="F-R7-400", status="pending")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1
        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_status"] is None

    def test_child_without_slot_counted_as_skipped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(child_db, spec_slot=None, status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.skipped_no_slot == 1
        assert result.stamped == 0

    def test_no_matching_slot_counted_as_skipped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(parent_db, spec_slot="F-R7-001", status="completed")
        _insert_feature(child_db, spec_slot="F-R7-999", status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1

    def test_multiple_slots_stamped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        for i in range(5):
            _insert_feature(parent_db, spec_slot=f"F-R7-{i:03d}", status="completed")
            _insert_feature(child_db, spec_slot=f"F-R7-{i:03d}", status="pending")

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 5
        assert result.skipped_no_slot == 0
        assert result.skipped_no_parent_match == 0

    def test_empty_dbs_return_zero_counts(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        result = inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_slot == 0
        assert result.skipped_no_parent_match == 0

    def test_none_parent_db_raises_value_error(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)
        with pytest.raises(ValueError):
            inherit_parent_status(parent_db_path=None, child_db_path=child_db)

    def test_empty_string_parent_db_raises_value_error(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)
        with pytest.raises(ValueError):
            inherit_parent_status(parent_db_path="", child_db_path=child_db)

    def test_missing_parent_db_raises_file_not_found(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)
        with pytest.raises(FileNotFoundError):
            inherit_parent_status(
                parent_db_path=tmp_path / "nonexistent.db",
                child_db_path=child_db,
            )

    def test_missing_child_db_raises_file_not_found(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        _init_db(parent_db)
        with pytest.raises(FileNotFoundError):
            inherit_parent_status(
                parent_db_path=parent_db,
                child_db_path=tmp_path / "nonexistent.db",
            )

    def test_parent_completed_at_is_stamped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(parent_db, spec_slot="F-R7-400", status="completed")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        inherit_parent_status(parent_db_path=parent_db, child_db_path=child_db)

        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_completed_at"] is not None

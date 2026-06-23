"""Tests for bob3.db_inheritance — public re-export of parent-gen DB inheritance API.

Verifies that the db_inheritance module correctly exposes inherit_parent_metadata
and that it behaves correctly when seeding bob_(N+1) from bob_N.
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.db_inheritance import (
    StampResult,
    inherit_parent_metadata,
    read_parent_features,
    stamp_child_row,
)


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


class TestDbInheritanceModule:
    def test_inherit_parent_metadata_is_callable(self):
        """The function is importable and callable."""
        assert callable(inherit_parent_metadata)

    def test_stamps_child_feature_by_spec_slot(self, tmp_path):
        """inherit_parent_metadata stamps a child feature whose spec_slot matches a parent."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        parent_fid = _insert_feature(parent_db, spec_slot="F-R7-400", status="completed")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert isinstance(result, StampResult)
        assert result.stamped == 1
        assert result.skipped_no_parent_match == 0

        conn = sqlite3.connect(str(child_db))
        row = conn.execute(
            "SELECT parent_status FROM features WHERE id=?", (child_fid,)
        ).fetchone()
        conn.close()
        assert row[0] == "completed"

    def test_skips_pending_parent_rows(self, tmp_path):
        """Parent rows with status='pending' are not copied to children."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-401", status="pending")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-401", status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1

        conn = sqlite3.connect(str(child_db))
        row = conn.execute(
            "SELECT parent_status FROM features WHERE id=?", (child_fid,)
        ).fetchone()
        conn.close()
        assert row[0] is None

    def test_skips_child_features_without_spec_slot(self, tmp_path):
        """Child features with NULL spec_slot are counted as skipped_no_slot."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-402", status="completed")
        _insert_feature(child_db, spec_slot=None, status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0
        assert result.skipped_no_slot == 1

    def test_stamps_needs_human_status(self, tmp_path):
        """needs_human parent status is propagated to the child."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-403", status="needs_human")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-403", status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 1
        conn = sqlite3.connect(str(child_db))
        row = conn.execute(
            "SELECT parent_status FROM features WHERE id=?", (child_fid,)
        ).fetchone()
        conn.close()
        assert row[0] == "needs_human"

    def test_stamps_regression_status(self, tmp_path):
        """regression parent status is propagated to the child."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-404", status="regression")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-404", status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 1
        conn = sqlite3.connect(str(child_db))
        row = conn.execute(
            "SELECT parent_status FROM features WHERE id=?", (child_fid,)
        ).fetchone()
        conn.close()
        assert row[0] == "regression"

    def test_missing_parent_db_raises(self, tmp_path):
        """FileNotFoundError raised when parent DB does not exist."""
        child_db = tmp_path / "child.db"
        _init_db(child_db)
        with pytest.raises(FileNotFoundError):
            inherit_parent_metadata(
                parent_db_path=tmp_path / "nonexistent.db",
                child_db_path=child_db,
            )

    def test_missing_child_db_raises(self, tmp_path):
        """FileNotFoundError raised when child DB does not exist."""
        parent_db = tmp_path / "parent.db"
        _init_db(parent_db)
        with pytest.raises(FileNotFoundError):
            inherit_parent_metadata(
                parent_db_path=parent_db,
                child_db_path=tmp_path / "nonexistent.db",
            )

    def test_empty_parent_db_returns_zero_stamped(self, tmp_path):
        """Empty parent DB returns stamped=0 without raising."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)
        _insert_feature(child_db, spec_slot="F-R7-405", status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0

    def test_multiple_features_stamped_correctly(self, tmp_path):
        """Multiple matching features are all stamped."""
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        slots = [f"F-R7-{i:03d}" for i in range(5)]
        for slot in slots:
            _insert_feature(parent_db, spec_slot=slot, status="completed")
            _insert_feature(child_db, spec_slot=slot, status="pending")

        result = inherit_parent_metadata(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 5

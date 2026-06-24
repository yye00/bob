"""Tests for parent-generation DB inheritance at seed time (e1b5bacb).

Covers :func:`bob3.orchestrator.parent_gen_inheritance.inherit_from_parent_db`.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.orchestrator.parent_gen_inheritance import (
    InheritanceResult,
    inherit_from_parent_db,
    _fetch_latest_evidence_hash,
    _load_child_features,
    _load_parent_rows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_db(path: pathlib.Path) -> None:
    """Create a minimal features + evidence_artifacts schema in a temp DB."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS features (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
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
    )
    conn.commit()
    conn.close()


def _insert_feature(
    path: pathlib.Path,
    *,
    spec_slot: str | None,
    status: str = "completed",
    updated_at: str | None = None,
) -> str:
    fid = str(uuid.uuid4())
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO features (id, project_id, spec_slot, status, updated_at) VALUES (?,?,?,?,?)",
        (fid, "proj-1", spec_slot, status, updated_at or datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return fid


def _insert_evidence(path: pathlib.Path, feature_id: str, content: str) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at) VALUES (?,?,?,1,?)",
        (str(uuid.uuid4()), feature_id, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def _read_child_row(path: pathlib.Path, feature_id: str) -> dict:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_status, parent_completed_at, parent_evidence_hash FROM features WHERE id=?",
        (feature_id,),
    ).fetchone()
    conn.close()
    return dict(row)


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


class TestInheritFromParentDb:
    def test_stamps_matching_completed_feature(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        parent_fid = _insert_feature(parent_db, spec_slot="F-R7-100", status="completed")
        _insert_evidence(parent_db, parent_fid, "output text")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-100", status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        assert result.skipped_no_slot == 0
        assert result.skipped_no_parent_match == 0

        row = _read_child_row(child_db, child_fid)
        assert row["parent_status"] == "completed"
        assert row["parent_completed_at"] is not None
        expected_hash = hashlib.sha256(b"output text").hexdigest()
        assert row["parent_evidence_hash"] == expected_hash

    def test_stamps_needs_human_parent(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-200", status="needs_human")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-200", status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        row = _read_child_row(child_db, child_fid)
        assert row["parent_status"] == "needs_human"

    def test_stamps_regression_parent(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-300", status="regression")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-300", status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        row = _read_child_row(child_db, child_fid)
        assert row["parent_status"] == "regression"

    def test_multiple_features_partially_matched(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-100", status="completed")
        # slot F-R7-200 exists only in child; no parent match
        child_fid_a = _insert_feature(child_db, spec_slot="F-R7-100", status="pending")
        child_fid_b = _insert_feature(child_db, spec_slot="F-R7-200", status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        assert result.skipped_no_parent_match == 1
        assert _read_child_row(child_db, child_fid_a)["parent_status"] == "completed"
        assert _read_child_row(child_db, child_fid_b)["parent_status"] is None


class TestSkippedCases:
    def test_skips_child_feature_with_no_slot(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        # No parent rows needed; child has no slot
        _insert_feature(child_db, spec_slot=None, status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_slot == 1

    def test_ignores_pending_parent_features(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        # Parent feature is pending — should NOT be used for inheritance
        _insert_feature(parent_db, spec_slot="F-R7-400", status="pending")
        _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1

    def test_ignores_failed_parent_features(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-500", status="failed")
        _insert_feature(child_db, spec_slot="F-R7-500", status="pending")

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1


class TestEvidenceHash:
    def test_returns_sha256_of_content(self, tmp_path):
        db_path = tmp_path / "test.db"
        _init_db(db_path)
        fid = _insert_feature(db_path, spec_slot="S1", status="completed")
        _insert_evidence(db_path, fid, "hello world")

        result = _fetch_latest_evidence_hash(db_path, fid)

        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_returns_none_when_no_evidence(self, tmp_path):
        db_path = tmp_path / "test.db"
        _init_db(db_path)
        fid = _insert_feature(db_path, spec_slot="S1", status="completed")

        result = _fetch_latest_evidence_hash(db_path, fid)

        assert result is None

    def test_returns_hash_of_most_recent_evidence(self, tmp_path):
        db_path = tmp_path / "test.db"
        _init_db(db_path)
        fid = _insert_feature(db_path, spec_slot="S1", status="completed")

        # Insert two artifacts; the second (later created_at) should win
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at) VALUES (?,?,?,1,?)",
            (str(uuid.uuid4()), fid, "old content", "2024-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at) VALUES (?,?,?,1,?)",
            (str(uuid.uuid4()), fid, "new content", "2024-01-02T00:00:00"),
        )
        conn.commit()
        conn.close()

        result = _fetch_latest_evidence_hash(db_path, fid)

        expected = hashlib.sha256(b"new content").hexdigest()
        assert result == expected


class TestErrorCases:
    def test_raises_when_parent_db_missing(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)

        with pytest.raises(FileNotFoundError, match="Parent DB not found"):
            inherit_from_parent_db(
                parent_db_path=tmp_path / "nonexistent.db",
                child_db_path=child_db,
            )

    def test_raises_when_child_db_missing(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        _init_db(parent_db)

        with pytest.raises(FileNotFoundError, match="Child DB not found"):
            inherit_from_parent_db(
                parent_db_path=parent_db,
                child_db_path=tmp_path / "nonexistent.db",
            )


class TestReturnType:
    def test_returns_inheritance_result_namedtuple(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        result = inherit_from_parent_db(parent_db_path=parent_db, child_db_path=child_db)

        assert isinstance(result, InheritanceResult)
        assert hasattr(result, "stamped")
        assert hasattr(result, "skipped_no_slot")
        assert hasattr(result, "skipped_no_parent_match")

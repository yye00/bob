"""Tests for bob.parent_gen_db — read_parent_features and stamp_child_row."""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob.parent_gen_db import read_parent_features, stamp_child_row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_db(path: pathlib.Path) -> None:
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


def _insert_evidence(path: pathlib.Path, feature_id: str, content: str, created_at: str | None = None) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at) VALUES (?,?,?,1,?)",
        (str(uuid.uuid4()), feature_id, content, created_at or datetime.now().isoformat()),
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
# Tests: read_parent_features
# ---------------------------------------------------------------------------


class TestReadParentFeatures:
    def test_returns_empty_dict_when_db_missing(self, tmp_path):
        result = read_parent_features(tmp_path / "no_such.db")
        assert result == {}

    def test_returns_empty_dict_for_string_missing_path(self, tmp_path):
        result = read_parent_features(str(tmp_path / "gone.db"))
        assert result == {}

    def test_returns_empty_dict_for_empty_db(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        result = read_parent_features(db)
        assert result == {}

    def test_includes_completed_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = read_parent_features(db)

        assert "F-R7-100" in result
        assert result["F-R7-100"]["status"] == "completed"

    def test_includes_needs_human_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-200", status="needs_human")

        result = read_parent_features(db)

        assert "F-R7-200" in result
        assert result["F-R7-200"]["status"] == "needs_human"

    def test_includes_regression_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-300", status="regression")

        result = read_parent_features(db)

        assert "F-R7-300" in result
        assert result["F-R7-300"]["status"] == "regression"

    def test_excludes_pending_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-400", status="pending")

        result = read_parent_features(db)

        assert "F-R7-400" not in result

    def test_excludes_failed_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-500", status="failed")

        result = read_parent_features(db)

        assert "F-R7-500" not in result

    def test_excludes_features_without_spec_slot(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot=None, status="completed")

        result = read_parent_features(db)

        assert result == {}

    def test_row_contains_spec_slot(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = read_parent_features(db)

        assert result["F-R7-100"]["spec_slot"] == "F-R7-100"

    def test_row_contains_id(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = read_parent_features(db)

        assert result["F-R7-100"]["id"] == fid

    def test_row_contains_updated_at(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        ts = "2026-01-15T10:00:00"
        _insert_feature(db, spec_slot="F-R7-100", status="completed", updated_at=ts)

        result = read_parent_features(db)

        assert result["F-R7-100"]["updated_at"] == ts

    def test_evidence_hash_sha256_of_content(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-100", status="completed")
        _insert_evidence(db, fid, "test output")

        result = read_parent_features(db)

        expected = hashlib.sha256(b"test output").hexdigest()
        assert result["F-R7-100"]["evidence_hash"] == expected

    def test_evidence_hash_none_when_no_evidence(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = read_parent_features(db)

        assert result["F-R7-100"]["evidence_hash"] is None

    def test_evidence_hash_uses_most_recent(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-100", status="completed")
        _insert_evidence(db, fid, "old content", created_at="2024-01-01T00:00:00")
        _insert_evidence(db, fid, "new content", created_at="2024-01-02T00:00:00")

        result = read_parent_features(db)

        expected = hashlib.sha256(b"new content").hexdigest()
        assert result["F-R7-100"]["evidence_hash"] == expected

    def test_multiple_features_returned(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")
        _insert_feature(db, spec_slot="F-R7-200", status="needs_human")
        _insert_feature(db, spec_slot="F-R7-300", status="regression")
        _insert_feature(db, spec_slot="F-R7-400", status="pending")

        result = read_parent_features(db)

        assert set(result.keys()) == {"F-R7-100", "F-R7-200", "F-R7-300"}

    def test_accepts_string_path(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = read_parent_features(str(db))

        assert "F-R7-100" in result


# ---------------------------------------------------------------------------
# Tests: stamp_child_row
# ---------------------------------------------------------------------------


class TestStampChildRow:
    def test_writes_parent_status(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-100", status="pending")

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at="2026-01-01T00:00:00",
            parent_evidence_hash="abc123",
        )

        row = _read_child_row(db, fid)
        assert row["parent_status"] == "completed"

    def test_writes_parent_completed_at(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-200", status="pending")
        ts = "2026-05-01T12:00:00"

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at=ts,
            parent_evidence_hash=None,
        )

        row = _read_child_row(db, fid)
        assert row["parent_completed_at"] == ts

    def test_writes_parent_evidence_hash(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-300", status="pending")
        h = "deadbeef" * 8

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="regression",
            parent_completed_at=None,
            parent_evidence_hash=h,
        )

        row = _read_child_row(db, fid)
        assert row["parent_evidence_hash"] == h

    def test_accepts_none_for_optional_fields(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-400", status="pending")

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="needs_human",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )

        row = _read_child_row(db, fid)
        assert row["parent_status"] == "needs_human"
        assert row["parent_evidence_hash"] is None
        assert row["parent_completed_at"] is None

    def test_all_fields_written_atomically(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-500", status="pending")

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at="2026-03-15T08:30:00",
            parent_evidence_hash="cafebabe" * 8,
        )

        row = _read_child_row(db, fid)
        assert row["parent_status"] == "completed"
        assert row["parent_completed_at"] == "2026-03-15T08:30:00"
        assert row["parent_evidence_hash"] == "cafebabe" * 8

    def test_accepts_string_path(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-600", status="pending")

        stamp_child_row(
            child_db_path=str(db),
            feature_id=fid,
            parent_status="completed",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )

        row = _read_child_row(db, fid)
        assert row["parent_status"] == "completed"

    def test_stamps_needs_human_status(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-700", status="pending")

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="needs_human",
            parent_completed_at="2026-04-01T09:00:00",
            parent_evidence_hash=None,
        )

        row = _read_child_row(db, fid)
        assert row["parent_status"] == "needs_human"

    def test_stamps_regression_status(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-800", status="pending")

        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="regression",
            parent_completed_at=None,
            parent_evidence_hash="hash123",
        )

        row = _read_child_row(db, fid)
        assert row["parent_status"] == "regression"

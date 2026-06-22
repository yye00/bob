"""Tests for bob3.parent_gen_db_inheritance — read_parent_features and stamp_child_row."""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.parent_gen_db_inheritance import read_parent_features, stamp_child_row
from tests.test_spawn_next_generation import assert_spawn_script_invokes_parent_gen_inheritance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    updated_at: str | None = None,
) -> str:
    fid = str(uuid.uuid4())
    ts = updated_at or datetime.now().isoformat()
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO features (id, project_id, spec_slot, status, updated_at)"
        " VALUES (?,?,?,?,?)",
        (fid, "proj-1", spec_slot, status, ts),
    )
    conn.commit()
    conn.close()
    return fid


def _insert_evidence(path: pathlib.Path, feature_id: str, content: str) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at)"
        " VALUES (?,?,?,1,?)",
        (str(uuid.uuid4()), feature_id, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def _read_feature(path: pathlib.Path, feature_id: str) -> dict:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM features WHERE id = ?", (feature_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Tests for read_parent_features
# ---------------------------------------------------------------------------


class TestReadParentFeatures:
    def test_returns_completed_features_by_slot(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-400", status="completed")
        result = read_parent_features(db)
        assert "F-R7-400" in result
        row = result["F-R7-400"]
        assert row.id == fid
        assert row.status == "completed"
        assert row.spec_slot == "F-R7-400"

    def test_returns_needs_human_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-401", status="needs_human")
        result = read_parent_features(db)
        assert "F-R7-401" in result
        assert result["F-R7-401"].status == "needs_human"

    def test_returns_regression_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-402", status="regression")
        result = read_parent_features(db)
        assert "F-R7-402" in result
        assert result["F-R7-402"].status == "regression"

    def test_excludes_pending_features(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-403", status="pending")
        result = read_parent_features(db)
        assert "F-R7-403" not in result

    def test_excludes_features_without_spec_slot(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot=None, status="completed")
        result = read_parent_features(db)
        assert len(result) == 0

    def test_computes_evidence_hash(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-404", status="completed")
        content = "some evidence payload"
        _insert_evidence(db, fid, content)
        expected = hashlib.sha256(content.encode()).hexdigest()
        result = read_parent_features(db)
        assert result["F-R7-404"].evidence_hash == expected

    def test_evidence_hash_none_when_no_evidence(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-405", status="completed")
        result = read_parent_features(db)
        assert result["F-R7-405"].evidence_hash is None

    def test_raises_file_not_found_for_missing_db(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_parent_features(tmp_path / "nonexistent.db")

    def test_raises_value_error_for_none_path(self):
        with pytest.raises(ValueError):
            read_parent_features(None)

    def test_returns_multiple_slots(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        for slot in ["F-R7-100", "F-R7-200", "F-R7-300"]:
            _insert_feature(db, spec_slot=slot, status="completed")
        result = read_parent_features(db)
        assert len(result) == 3
        assert all(s in result for s in ["F-R7-100", "F-R7-200", "F-R7-300"])


# ---------------------------------------------------------------------------
# Tests for stamp_child_row
# ---------------------------------------------------------------------------


class TestStampChildRow:
    def test_stamps_parent_status(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-400", status="pending")
        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at="2026-01-01T12:00:00",
            parent_evidence_hash="abc123",
        )
        row = _read_feature(db, fid)
        assert row["parent_status"] == "completed"

    def test_stamps_parent_completed_at(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-400", status="pending")
        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at="2026-01-01T12:00:00",
            parent_evidence_hash=None,
        )
        row = _read_feature(db, fid)
        assert row["parent_completed_at"] == "2026-01-01T12:00:00"

    def test_stamps_parent_evidence_hash(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-400", status="pending")
        h = hashlib.sha256(b"payload").hexdigest()
        stamp_child_row(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at=None,
            parent_evidence_hash=h,
        )
        row = _read_feature(db, fid)
        assert row["parent_evidence_hash"] == h

    def test_stamps_null_evidence_hash(self, tmp_path):
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
        row = _read_feature(db, fid)
        assert row["parent_evidence_hash"] is None

    def test_raises_file_not_found_for_missing_db(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            stamp_child_row(
                child_db_path=tmp_path / "nonexistent.db",
                feature_id=str(uuid.uuid4()),
                parent_status="completed",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )

    def test_raises_value_error_for_empty_feature_id(self, tmp_path):
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

    def test_raises_value_error_for_empty_parent_status(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        with pytest.raises(ValueError):
            stamp_child_row(
                child_db_path=db,
                feature_id=str(uuid.uuid4()),
                parent_status="",
                parent_completed_at=None,
                parent_evidence_hash=None,
            )


# ---------------------------------------------------------------------------
# Integration: read_parent_features + stamp_child_row round-trip
# ---------------------------------------------------------------------------


class TestSpawnIntegration:
    def test_spawn_script_invokes_parent_gen_inheritance(self):
        """Verify spawn_next_generation.sh is wired to call parent-gen inheritance."""
        assert_spawn_script_invokes_parent_gen_inheritance()


class TestRoundTrip:
    def test_full_round_trip(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        parent_fid = _insert_feature(
            parent_db, spec_slot="F-R7-400", status="completed", updated_at="2026-01-01T10:00:00"
        )
        _insert_evidence(parent_db, parent_fid, "payload")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        parent_features = read_parent_features(parent_db)
        assert "F-R7-400" in parent_features
        pf = parent_features["F-R7-400"]
        stamp_child_row(
            child_db_path=child_db,
            feature_id=child_fid,
            parent_status=pf.status,
            parent_completed_at=pf.updated_at,
            parent_evidence_hash=pf.evidence_hash,
        )

        row = _read_feature(child_db, child_fid)
        assert row["parent_status"] == "completed"
        assert row["parent_completed_at"] == "2026-01-01T10:00:00"
        expected_hash = hashlib.sha256(b"payload").hexdigest()
        assert row["parent_evidence_hash"] == expected_hash

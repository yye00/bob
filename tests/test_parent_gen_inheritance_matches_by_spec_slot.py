"""Tests for match_by_spec_slot and stamp_provenance in parent_gen_inheritance.

Covers:
- :func:`bob.orchestrator.parent_gen_inheritance.match_by_spec_slot`
- :func:`bob.orchestrator.parent_gen_inheritance.stamp_provenance`
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob.orchestrator.parent_gen_inheritance import (
    match_by_spec_slot,
    stamp_provenance,
)


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


def _read_row(path: pathlib.Path, feature_id: str) -> dict:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_status, parent_completed_at, parent_evidence_hash FROM features WHERE id=?",
        (feature_id,),
    ).fetchone()
    conn.close()
    return dict(row)


# ---------------------------------------------------------------------------
# Tests: match_by_spec_slot
# ---------------------------------------------------------------------------


class TestMatchBySpecSlot:
    def test_returns_dict_keyed_by_spec_slot(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = match_by_spec_slot(db)

        assert isinstance(result, dict)
        assert "F-R7-100" in result

    def test_includes_completed_status(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-200", status="completed")

        result = match_by_spec_slot(db)

        assert "F-R7-200" in result
        assert result["F-R7-200"]["status"] == "completed"

    def test_includes_needs_human_status(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-300", status="needs_human")

        result = match_by_spec_slot(db)

        assert "F-R7-300" in result
        assert result["F-R7-300"]["status"] == "needs_human"

    def test_includes_regression_status(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-400", status="regression")

        result = match_by_spec_slot(db)

        assert "F-R7-400" in result
        assert result["F-R7-400"]["status"] == "regression"

    def test_excludes_pending_status(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-500", status="pending")

        result = match_by_spec_slot(db)

        assert "F-R7-500" not in result

    def test_excludes_failed_status(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-600", status="failed")

        result = match_by_spec_slot(db)

        assert "F-R7-600" not in result

    def test_excludes_features_without_spec_slot(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot=None, status="completed")

        result = match_by_spec_slot(db)

        assert result == {}

    def test_returns_empty_dict_for_empty_db(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)

        result = match_by_spec_slot(db)

        assert result == {}

    def test_multiple_slots_all_returned(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")
        _insert_feature(db, spec_slot="F-R7-200", status="needs_human")
        _insert_feature(db, spec_slot="F-R7-300", status="regression")
        _insert_feature(db, spec_slot="F-R7-400", status="pending")  # excluded

        result = match_by_spec_slot(db)

        assert set(result.keys()) == {"F-R7-100", "F-R7-200", "F-R7-300"}

    def test_row_contains_id_field(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = match_by_spec_slot(db)

        assert result["F-R7-100"]["id"] == fid

    def test_accepts_string_path(self, tmp_path):
        db = tmp_path / "parent.db"
        _init_db(db)
        _insert_feature(db, spec_slot="F-R7-100", status="completed")

        result = match_by_spec_slot(str(db))

        assert "F-R7-100" in result

    def test_returns_empty_dict_when_db_missing(self, tmp_path):
        missing = tmp_path / "no_such.db"
        result = match_by_spec_slot(missing)
        assert result == {}


# ---------------------------------------------------------------------------
# Tests: stamp_provenance
# ---------------------------------------------------------------------------


class TestStampProvenance:
    def test_writes_parent_status(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-100", status="pending")

        stamp_provenance(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at="2026-01-01T00:00:00",
            parent_evidence_hash="abc123",
        )

        row = _read_row(db, fid)
        assert row["parent_status"] == "completed"

    def test_writes_parent_completed_at(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-200", status="pending")
        ts = "2026-05-01T12:00:00"

        stamp_provenance(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at=ts,
            parent_evidence_hash=None,
        )

        row = _read_row(db, fid)
        assert row["parent_completed_at"] == ts

    def test_writes_parent_evidence_hash(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-300", status="pending")
        h = "deadbeef" * 8

        stamp_provenance(
            child_db_path=db,
            feature_id=fid,
            parent_status="regression",
            parent_completed_at=None,
            parent_evidence_hash=h,
        )

        row = _read_row(db, fid)
        assert row["parent_evidence_hash"] == h

    def test_accepts_none_evidence_hash(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-400", status="pending")

        stamp_provenance(
            child_db_path=db,
            feature_id=fid,
            parent_status="needs_human",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )

        row = _read_row(db, fid)
        assert row["parent_status"] == "needs_human"
        assert row["parent_evidence_hash"] is None

    def test_accepts_string_path(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-500", status="pending")

        stamp_provenance(
            child_db_path=str(db),
            feature_id=fid,
            parent_status="completed",
            parent_completed_at=None,
            parent_evidence_hash=None,
        )

        row = _read_row(db, fid)
        assert row["parent_status"] == "completed"

    def test_all_three_fields_written_atomically(self, tmp_path):
        db = tmp_path / "child.db"
        _init_db(db)
        fid = _insert_feature(db, spec_slot="F-R7-600", status="pending")

        stamp_provenance(
            child_db_path=db,
            feature_id=fid,
            parent_status="completed",
            parent_completed_at="2026-03-15T08:30:00",
            parent_evidence_hash="cafebabe" * 8,
        )

        row = _read_row(db, fid)
        assert row["parent_status"] == "completed"
        assert row["parent_completed_at"] == "2026-03-15T08:30:00"
        assert row["parent_evidence_hash"] == "cafebabe" * 8

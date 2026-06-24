"""Tests for bob3.parent_gen.stamp_parent_metadata.

Covers:
- Normal stamping of child features matched by spec_slot
- Empty parent DB returns well-defined result (not a crash)
- Zero-row child DB returns well-defined result (not a crash)
- Invalid input raises ValueError, not silent success
- Missing parent DB path raises FileNotFoundError
- Features without spec_slot are skipped
- Features with no parent match are skipped
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid

import pytest

from bob3.parent_gen import stamp_parent_metadata


# ---------------------------------------------------------------------------
# Minimal DB schema shared by helpers
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


def _make_db(path: pathlib.Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _insert_feature(
    db_path: pathlib.Path,
    *,
    feature_id: str | None = None,
    spec_slot: str | None = None,
    status: str = "pending",
    updated_at: str = "2026-01-01T00:00:00",
) -> str:
    fid = feature_id or str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO features (id, spec_slot, status, updated_at) VALUES (?, ?, ?, ?)",
        (fid, spec_slot, status, updated_at),
    )
    conn.commit()
    conn.close()
    return fid


def _insert_evidence(
    db_path: pathlib.Path,
    feature_id: str,
    content: str = "some evidence",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at)"
        " VALUES (?, ?, ?, 1, '2026-01-01T00:00:00')",
        (str(uuid.uuid4()), feature_id, content),
    )
    conn.commit()
    conn.close()


def _read_feature(db_path: pathlib.Path, feature_id: str) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM features WHERE id = ?", (feature_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStampParentMetadataBasic:
    """Happy-path stamping."""

    def test_stamps_matched_child_feature(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        parent_fid = _insert_feature(
            parent_db,
            spec_slot="F-R7-400",
            status="completed",
            updated_at="2026-05-01T12:00:00",
        )
        child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

        result = stamp_parent_metadata(
            parent_db_path=parent_db, child_db_path=child_db
        )

        assert result.stamped == 1
        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_status"] == "completed"
        assert child_row["parent_completed_at"] == "2026-05-01T12:00:00"

    def test_stamps_evidence_hash_when_artifact_present(self, tmp_path):
        import hashlib

        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        parent_fid = _insert_feature(
            parent_db, spec_slot="F-R7-401", status="completed"
        )
        _insert_evidence(parent_db, parent_fid, content="test evidence content")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-401", status="pending")

        stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        child_row = _read_feature(child_db, child_fid)
        expected_hash = hashlib.sha256(b"test evidence content").hexdigest()
        assert child_row["parent_evidence_hash"] == expected_hash

    def test_evidence_hash_is_none_when_no_artifact(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-402", status="needs_human")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-402", status="pending")

        stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        child_row = _read_feature(child_db, child_fid)
        assert child_row["parent_evidence_hash"] is None

    def test_stamps_needs_human_status(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-403", status="needs_human")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-403", status="pending")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        assert _read_feature(child_db, child_fid)["parent_status"] == "needs_human"

    def test_stamps_regression_status(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-404", status="regression")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-404", status="pending")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 1
        assert _read_feature(child_db, child_fid)["parent_status"] == "regression"


class TestStampParentMetadataSkipCases:
    """Rows that should be skipped, not stamped."""

    def test_skips_child_without_spec_slot(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-500", status="completed")
        child_fid = _insert_feature(child_db, spec_slot=None, status="pending")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_slot >= 1
        assert _read_feature(child_db, child_fid)["parent_status"] is None

    def test_skips_child_with_no_matching_parent_slot(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-500", status="completed")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-999", status="pending")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_parent_match >= 1
        assert _read_feature(child_db, child_fid)["parent_status"] is None

    def test_ignores_parent_rows_with_non_qualifying_status(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-501", status="pending")
        _insert_feature(parent_db, spec_slot="F-R7-502", status="executing")
        _insert_feature(parent_db, spec_slot="F-R7-503", status="failed")
        child_fid_a = _insert_feature(child_db, spec_slot="F-R7-501")
        child_fid_b = _insert_feature(child_db, spec_slot="F-R7-502")
        child_fid_c = _insert_feature(child_db, spec_slot="F-R7-503")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        for fid in (child_fid_a, child_fid_b, child_fid_c):
            assert _read_feature(child_db, fid)["parent_status"] is None


class TestStampParentMetadataBoundaryCases:
    """Boundary cases: empty/zero inputs must return well-defined results, not crash."""

    def test_empty_parent_db_returns_zero_stamped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        # parent has no rows at all
        _insert_feature(child_db, spec_slot="F-R7-600", status="pending")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert isinstance(result.skipped_no_slot, int)
        assert isinstance(result.skipped_no_parent_match, int)

    def test_empty_child_db_returns_zero_stamped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        # parent has rows but child is empty
        _insert_feature(parent_db, spec_slot="F-R7-700", status="completed")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0

    def test_both_dbs_empty_returns_well_defined_result(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 0
        assert result.skipped_no_slot == 0
        assert result.skipped_no_parent_match == 0


class TestStampParentMetadataInvalidInput:
    """Invalid inputs must raise ValueError or FileNotFoundError, not silently succeed."""

    def test_raises_when_parent_db_does_not_exist(self, tmp_path):
        child_db = tmp_path / "child.db"
        _make_db(child_db)
        nonexistent = tmp_path / "nonexistent.db"

        with pytest.raises(FileNotFoundError):
            stamp_parent_metadata(parent_db_path=nonexistent, child_db_path=child_db)

    def test_raises_when_child_db_does_not_exist(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        _make_db(parent_db)
        nonexistent = tmp_path / "nonexistent_child.db"

        with pytest.raises(FileNotFoundError):
            stamp_parent_metadata(parent_db_path=parent_db, child_db_path=nonexistent)

    def test_raises_value_error_on_none_parent_db_path(self, tmp_path):
        child_db = tmp_path / "child.db"
        _make_db(child_db)

        with pytest.raises((TypeError, ValueError)):
            stamp_parent_metadata(parent_db_path=None, child_db_path=child_db)  # type: ignore[arg-type]

    def test_does_not_silently_succeed_with_empty_string_parent_path(self, tmp_path):
        child_db = tmp_path / "child.db"
        _make_db(child_db)

        with pytest.raises((FileNotFoundError, ValueError, OSError)):
            stamp_parent_metadata(parent_db_path="", child_db_path=child_db)


class TestStampParentMetadataMultipleFeatures:
    """Multiple features stamped in a single call."""

    def test_stamps_multiple_matched_features(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        slots = ["F-R7-800", "F-R7-801", "F-R7-802"]
        for slot in slots:
            _insert_feature(parent_db, spec_slot=slot, status="completed")
            _insert_feature(child_db, spec_slot=slot, status="pending")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 3

    def test_mixed_match_counts_are_accurate(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _make_db(parent_db)
        _make_db(child_db)

        # 2 matched, 1 no-slot child, 1 no-parent-match child
        _insert_feature(parent_db, spec_slot="F-R7-900", status="completed")
        _insert_feature(parent_db, spec_slot="F-R7-901", status="completed")
        _insert_feature(child_db, spec_slot="F-R7-900")
        _insert_feature(child_db, spec_slot="F-R7-901")
        _insert_feature(child_db, spec_slot=None)
        _insert_feature(child_db, spec_slot="F-R7-999")

        result = stamp_parent_metadata(parent_db_path=parent_db, child_db_path=child_db)

        assert result.stamped == 2
        assert result.skipped_no_slot == 1
        assert result.skipped_no_parent_match == 1

"""Tests for bob.seed_inheritance.apply_parent_generation_data."""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob.seed_inheritance import apply_parent_generation_data, SeedInheritanceResult


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
        "INSERT INTO features (id, project_id, spec_slot, status, updated_at) VALUES (?,?,?,?,?)",
        (fid, "proj-1", spec_slot, status, ts),
    )
    conn.commit()
    conn.close()
    return fid


def _get_parent_fields(path: pathlib.Path, fid: str) -> dict:
    conn = sqlite3.connect(str(path))
    row = conn.execute(
        "SELECT parent_status, parent_completed_at, parent_evidence_hash FROM features WHERE id=?",
        (fid,),
    ).fetchone()
    conn.close()
    return {
        "parent_status": row[0],
        "parent_completed_at": row[1],
        "parent_evidence_hash": row[2],
    }


class TestApplyParentGenerationData:
    def test_stamps_matched_child_rows(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-001", status="completed")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-001", status="pending")

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 1
        fields = _get_parent_fields(child_db, child_fid)
        assert fields["parent_status"] == "completed"

    def test_stamps_needs_human_and_regression(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-001", status="needs_human")
        _insert_feature(parent_db, spec_slot="F-R7-002", status="regression")
        child1 = _insert_feature(child_db, spec_slot="F-R7-001", status="pending")
        child2 = _insert_feature(child_db, spec_slot="F-R7-002", status="pending")

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 2
        assert _get_parent_fields(child_db, child1)["parent_status"] == "needs_human"
        assert _get_parent_fields(child_db, child2)["parent_status"] == "regression"

    def test_skips_pending_parent_rows(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-001", status="pending")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-001", status="pending")

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1
        assert _get_parent_fields(child_db, child_fid)["parent_status"] is None

    def test_skips_child_rows_with_no_slot(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-001", status="completed")
        child_fid = _insert_feature(child_db, spec_slot=None, status="pending")

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0
        assert result.skipped_no_slot == 1
        assert _get_parent_fields(child_db, child_fid)["parent_status"] is None

    def test_skips_child_rows_with_no_parent_match(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(parent_db, spec_slot="F-R7-001", status="completed")
        child_fid = _insert_feature(child_db, spec_slot="F-R7-999", status="pending")

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1
        assert _get_parent_fields(child_db, child_fid)["parent_status"] is None

    def test_returns_seed_inheritance_result_type(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert isinstance(result, SeedInheritanceResult)

    def test_empty_parent_db_returns_all_skipped(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        _insert_feature(child_db, spec_slot="F-R7-001", status="pending")

        result = apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        assert result.stamped == 0
        assert result.skipped_no_parent_match == 1

    def test_missing_parent_db_raises_file_not_found(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)

        with pytest.raises(FileNotFoundError):
            apply_parent_generation_data(
                parent_db_path=tmp_path / "nonexistent.db",
                child_db_path=child_db,
            )

    def test_missing_child_db_raises_file_not_found(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        _init_db(parent_db)

        with pytest.raises(FileNotFoundError):
            apply_parent_generation_data(
                parent_db_path=parent_db,
                child_db_path=tmp_path / "nonexistent.db",
            )

    def test_none_parent_db_raises_value_error(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)

        with pytest.raises((ValueError, TypeError)):
            apply_parent_generation_data(
                parent_db_path=None,
                child_db_path=child_db,
            )

    def test_copies_parent_completed_at(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        child_db = tmp_path / "child.db"
        _init_db(parent_db)
        _init_db(child_db)

        ts = "2026-01-01T12:00:00"
        _insert_feature(parent_db, spec_slot="F-R7-001", status="completed", updated_at=ts)
        child_fid = _insert_feature(child_db, spec_slot="F-R7-001", status="pending")

        apply_parent_generation_data(
            parent_db_path=parent_db,
            child_db_path=child_db,
        )

        fields = _get_parent_fields(child_db, child_fid)
        assert fields["parent_completed_at"] == ts


class TestSpawnNextGenerationIntegration:
    def test_apply_parent_generation_data_importable_from_spawn_next_generation(self):
        from bob.spawn_next_generation import apply_parent_generation_data as fn
        assert callable(fn)

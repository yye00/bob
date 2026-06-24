"""Tests that parent_gen_inheritance never raises FileNotFoundError for missing parent DB.

Covers :func:`bob3.orchestrator.parent_gen_inheritance.handle_missing_parent_db`
and the safe path through :func:`match_by_spec_slot` when the parent DB is absent.
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.orchestrator.parent_gen_inheritance import (
    handle_missing_parent_db,
    match_by_spec_slot,
    inherit_from_parent_db,
)


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


class TestHandleMissingParentDb:
    def test_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "does_not_exist.db"
        result = handle_missing_parent_db(missing)
        assert result == {}

    def test_never_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "absolutely_missing.db"
        # Must not raise FileNotFoundError regardless of path
        try:
            result = handle_missing_parent_db(missing)
        except FileNotFoundError:
            pytest.fail("handle_missing_parent_db raised FileNotFoundError")
        assert isinstance(result, dict)

    def test_returns_dict_type(self, tmp_path):
        result = handle_missing_parent_db(tmp_path / "no.db")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_accepts_string_path(self, tmp_path):
        missing = str(tmp_path / "missing.db")
        result = handle_missing_parent_db(missing)
        assert result == {}

    def test_accepts_pathlib_path(self, tmp_path):
        missing = tmp_path / "missing.db"
        assert isinstance(missing, pathlib.Path)
        result = handle_missing_parent_db(missing)
        assert result == {}


class TestMatchBySpecSlotMissingDb:
    def test_returns_empty_dict_when_parent_db_absent(self, tmp_path):
        missing = tmp_path / "no_parent.db"
        result = match_by_spec_slot(missing)
        assert result == {}

    def test_never_raises_when_parent_db_absent(self, tmp_path):
        missing = tmp_path / "vanished.db"
        try:
            result = match_by_spec_slot(missing)
        except FileNotFoundError:
            pytest.fail("match_by_spec_slot raised FileNotFoundError for missing parent DB")
        assert isinstance(result, dict)

    def test_returns_empty_dict_for_string_path_missing(self, tmp_path):
        missing = str(tmp_path / "nope.db")
        result = match_by_spec_slot(missing)
        assert result == {}


class TestInheritFromParentDbRaisesOnMissing:
    """inherit_from_parent_db intentionally raises — only handle_missing_parent_db is safe."""

    def test_raises_when_parent_db_missing(self, tmp_path):
        child_db = tmp_path / "child.db"
        _init_db(child_db)
        with pytest.raises(FileNotFoundError):
            inherit_from_parent_db(
                parent_db_path=tmp_path / "ghost.db",
                child_db_path=child_db,
            )

    def test_raises_when_child_db_missing(self, tmp_path):
        parent_db = tmp_path / "parent.db"
        _init_db(parent_db)
        with pytest.raises(FileNotFoundError):
            inherit_from_parent_db(
                parent_db_path=parent_db,
                child_db_path=tmp_path / "ghost.db",
            )

"""Tests the error path when spec_slot column is absent from features table.

Acceptance criterion:
- pytest: tests/test_convergence_error_path_missing_spec_slot_column.py
  asserts compares_by_spec_slot raises ValueError with message containing
  "spec_slot" when column absent
"""

from __future__ import annotations

import sqlite3
import pathlib

import pytest


def _make_db_without_spec_slot(path: pathlib.Path) -> None:
    """Create a minimal SQLite db with a features table that has NO spec_slot column."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


class TestMissingSpecSlotColumn:
    def test_compares_by_spec_slot_raises_value_error_when_column_absent(
        self, tmp_path, monkeypatch
    ):
        """compares_by_spec_slot must raise ValueError if spec_slot column is absent."""
        from bob3.orchestrator.convergence import compares_by_spec_slot

        db = tmp_path / "no_slot.db"
        _make_db_without_spec_slot(db)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db))

        with pytest.raises(ValueError) as exc_info:
            compares_by_spec_slot()

        assert "spec_slot" in str(exc_info.value), (
            f"ValueError message must mention 'spec_slot', got: {exc_info.value}"
        )

    def test_error_message_contains_spec_slot(self, tmp_path, monkeypatch):
        """The ValueError message must contain the string 'spec_slot'."""
        from bob3.orchestrator.convergence import compares_by_spec_slot

        db = tmp_path / "no_slot2.db"
        _make_db_without_spec_slot(db)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db))

        try:
            compares_by_spec_slot()
            pytest.fail("Expected ValueError was not raised")
        except ValueError as e:
            assert "spec_slot" in str(e)

    def test_no_error_when_column_present(self, tmp_path, monkeypatch):
        """compares_by_spec_slot must NOT raise when spec_slot column exists."""
        from bob3.orchestrator.convergence import compares_by_spec_slot
        from bob3.db import init_database

        db = tmp_path / "with_slot.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db))
        init_database(db_path=db)

        # Should not raise
        result = compares_by_spec_slot()
        assert result is True

    def test_nonexistent_db_does_not_raise(self, tmp_path, monkeypatch):
        """compares_by_spec_slot must not raise when BOB3_DATABASE_PATH points to
        a non-existent file (db hasn't been created yet — benign startup case)."""
        from bob3.orchestrator.convergence import compares_by_spec_slot

        db = tmp_path / "does_not_exist.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db))

        # Must not raise — just returns True since db doesn't exist yet
        result = compares_by_spec_slot()
        assert result is True

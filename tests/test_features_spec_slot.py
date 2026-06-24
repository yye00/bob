"""Tests for bob.features.add_spec_slot_column.

AC: File exists: src/bob/features.py
AC: Function defined: bob.features.add_spec_slot_column
AC: pytest: tests/test_features_spec_slot.py
"""

from __future__ import annotations

import pathlib
import sqlite3
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_db(db_path: pathlib.Path) -> None:
    """Create a minimal features table (without spec_slot) in db_path."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'proj',
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _get_columns(db_path: pathlib.Path) -> set:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


class TestFeaturesModuleStructure:
    def test_features_module_importable(self):
        """bob.features must be importable."""
        import bob.features  # noqa: F401

    def test_add_spec_slot_column_callable(self):
        """bob.features.add_spec_slot_column must be a callable."""
        from bob.features import add_spec_slot_column

        assert callable(add_spec_slot_column)

    def test_add_spec_slot_column_accepts_db_path(self):
        """add_spec_slot_column must accept a db_path keyword argument."""
        import inspect
        from bob.features import add_spec_slot_column

        sig = inspect.signature(add_spec_slot_column)
        assert "db_path" in sig.parameters


# ---------------------------------------------------------------------------
# add_spec_slot_column behaviour
# ---------------------------------------------------------------------------


class TestAddSpecSlotColumn:
    def test_adds_spec_slot_column(self, tmp_path):
        """add_spec_slot_column must add spec_slot to the features table."""
        from bob.features import add_spec_slot_column

        db_path = tmp_path / "test.db"
        _init_db(db_path)

        assert "spec_slot" not in _get_columns(db_path)

        add_spec_slot_column(db_path=db_path)

        assert "spec_slot" in _get_columns(db_path)

    def test_idempotent_on_existing_column(self, tmp_path):
        """Calling add_spec_slot_column twice must not raise."""
        from bob.features import add_spec_slot_column

        db_path = tmp_path / "test.db"
        _init_db(db_path)

        add_spec_slot_column(db_path=db_path)
        add_spec_slot_column(db_path=db_path)  # must not raise

        assert "spec_slot" in _get_columns(db_path)

    def test_preserves_existing_rows(self, tmp_path):
        """add_spec_slot_column must not delete existing feature rows."""
        from bob.features import add_spec_slot_column

        db_path = tmp_path / "test.db"
        _init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO features (id, name) VALUES (?, ?)",
            ("feat-1", "Auth System"),
        )
        conn.commit()
        conn.close()

        add_spec_slot_column(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id, name FROM features").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0] == ("feat-1", "Auth System")

    def test_spec_slot_defaults_to_null(self, tmp_path):
        """Existing rows must have spec_slot = NULL after column is added."""
        from bob.features import add_spec_slot_column

        db_path = tmp_path / "test.db"
        _init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO features (id, name) VALUES (?, ?)",
            ("feat-1", "Dashboard"),
        )
        conn.commit()
        conn.close()

        add_spec_slot_column(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT spec_slot FROM features WHERE id = ?", ("feat-1",)).fetchone()
        conn.close()

        assert row is not None
        assert row[0] is None

    def test_backfills_from_spec_yaml(self, tmp_path):
        """add_spec_slot_column with spec_path must backfill matching rows."""
        from bob.features import add_spec_slot_column

        db_path = tmp_path / "test.db"
        _init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO features (id, name) VALUES (?, ?)",
            ("feat-1", "Auth System"),
        )
        conn.execute(
            "INSERT INTO features (id, name) VALUES (?, ?)",
            ("feat-2", "Dashboard"),
        )
        conn.commit()
        conn.close()

        spec_content = textwrap.dedent("""\
            name: test-project
            features:
              F-R1-100:
                title: Auth System
                description: Handles auth
              F-R1-200:
                title: Dashboard
                description: Main dashboard
        """)
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(spec_content)

        add_spec_slot_column(db_path=db_path, spec_path=spec_path)

        conn = sqlite3.connect(str(db_path))
        rows = {
            r[0]: r[1]
            for r in conn.execute("SELECT id, spec_slot FROM features").fetchall()
        }
        conn.close()

        assert rows["feat-1"] == "F-R1-100"
        assert rows["feat-2"] == "F-R1-200"

    def test_unmatched_name_stays_null(self, tmp_path):
        """Features whose names don't match spec keys stay spec_slot=NULL."""
        from bob.features import add_spec_slot_column

        db_path = tmp_path / "test.db"
        _init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO features (id, name) VALUES (?, ?)",
            ("feat-x", "Unknown Feature"),
        )
        conn.commit()
        conn.close()

        spec_content = textwrap.dedent("""\
            name: test-project
            features:
              F-R1-100:
                title: Auth System
        """)
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(spec_content)

        add_spec_slot_column(db_path=db_path, spec_path=spec_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT spec_slot FROM features WHERE id = ?", ("feat-x",)).fetchone()
        conn.close()

        assert row is not None
        assert row[0] is None

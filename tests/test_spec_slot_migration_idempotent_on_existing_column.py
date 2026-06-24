"""Tests that add_spec_slot.upgrade() is idempotent when spec_slot already exists.

Acceptance criterion:
- pytest: tests/test_spec_slot_migration_idempotent_on_existing_column.py
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database
    init_database()
    return p


class TestIdempotentOnExistingColumn:
    def test_upgrade_twice_does_not_raise(self, db_path):
        """Running upgrade() twice must not raise (column already exists case)."""
        from bob3.migrations.add_spec_slot import upgrade

        # First call adds the column
        upgrade(db_path=db_path)

        # Second call must detect the column already exists and skip ALTER TABLE
        upgrade(db_path=db_path)  # must not raise

    def test_column_still_present_after_second_call(self, db_path):
        """spec_slot column must still be present after two upgrade() calls."""
        from bob3.migrations.add_spec_slot import upgrade

        upgrade(db_path=db_path)
        upgrade(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        finally:
            conn.close()

        assert "spec_slot" in cols

    def test_existing_spec_slot_values_preserved(self, db_path):
        """upgrade() must not overwrite existing spec_slot values on repeat calls."""
        from bob3.db import create_project, create_feature, get_feature
        from bob3.migrations.add_spec_slot import upgrade

        project = create_project(name="Test", workspace_path="/tmp/t")
        upgrade(db_path=db_path)

        f = create_feature(project_id=project.id, name="My Feature", spec_slot="F-R3-100")

        # Run upgrade again — existing value must survive
        upgrade(db_path=db_path)

        f_reloaded = get_feature(f.id)
        assert f_reloaded is not None
        assert f_reloaded.spec_slot == "F-R3-100"

    def test_upgrade_many_times_is_stable(self, db_path):
        """upgrade() must be safe to call N times without accumulating side effects."""
        from bob3.migrations.add_spec_slot import upgrade

        for _ in range(5):
            upgrade(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            # Verify there is exactly one spec_slot column (not duplicated)
            cols = [row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()]
        finally:
            conn.close()

        assert cols.count("spec_slot") == 1

"""Tests for the convergence detector: compares features by spec_slot, not UUID.

Acceptance criteria covered:
- File exists: src/bob/schema.py
- Function defined: bob.schema.add_spec_slot_column
- Function defined: bob.weekend_watchdog.check_convergence
- integration: bob.spawn_watchdog
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_db(db_path: Path, *, with_spec_slot: bool = True) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'proj',
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                spec_slot TEXT DEFAULT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _insert_feature(
    db_path: Path,
    *,
    name: str = "Feature",
    status: str = "completed",
    spec_slot: str | None = None,
) -> str:
    fid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO features (id, name, status, spec_slot) VALUES (?, ?, ?, ?)",
            (fid, name, status, spec_slot),
        )
        conn.commit()
    finally:
        conn.close()
    return fid


# ---------------------------------------------------------------------------
# bob.schema.add_spec_slot_column tests
# ---------------------------------------------------------------------------


class TestAddSpecSlotColumn:
    def test_adds_column_when_absent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE features (id TEXT PRIMARY KEY, name TEXT, status TEXT)")
        conn.commit()
        conn.close()

        from bob.schema import add_spec_slot_column

        result = add_spec_slot_column(db)
        assert result is True

        conn = sqlite3.connect(str(db))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        conn.close()
        assert "spec_slot" in cols

    def test_returns_false_when_column_already_exists(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE features (id TEXT PRIMARY KEY, name TEXT, status TEXT, spec_slot TEXT)"
        )
        conn.commit()
        conn.close()

        from bob.schema import add_spec_slot_column

        result = add_spec_slot_column(db)
        assert result is False

    def test_idempotent_on_repeated_calls(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE features (id TEXT PRIMARY KEY, name TEXT, status TEXT)")
        conn.commit()
        conn.close()

        from bob.schema import add_spec_slot_column

        add_spec_slot_column(db)
        # Second call must not raise
        result = add_spec_slot_column(db)
        assert result is False

    def test_raises_value_error_for_none(self):
        from bob.schema import add_spec_slot_column

        with pytest.raises(ValueError):
            add_spec_slot_column(None)  # type: ignore[arg-type]

    def test_raises_value_error_for_empty_string(self):
        from bob.schema import add_spec_slot_column

        with pytest.raises(ValueError):
            add_spec_slot_column("")

    def test_raises_value_error_for_non_path(self):
        from bob.schema import add_spec_slot_column

        with pytest.raises(ValueError):
            add_spec_slot_column(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# bob.weekend_watchdog.check_convergence tests
# ---------------------------------------------------------------------------


class TestWeekendWatchdogCheckConvergence:
    def test_converged_identical_spec_slots(self, tmp_path):
        from bob.orchestrator.weekend_watchdog import check_convergence

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        for db in [db_a, db_b]:
            _init_db(db)
            _insert_feature(db, name="Feature A", spec_slot="F-R1-001", status="completed")
            _insert_feature(db, name="Feature B", spec_slot="F-R1-002", status="completed")

        converged, diff = check_convergence(db_a, db_b)
        assert converged is True
        assert diff == set()

    def test_diverged_different_spec_slots(self, tmp_path):
        from bob.orchestrator.weekend_watchdog import check_convergence

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        _init_db(db_a)
        _init_db(db_b)
        _insert_feature(db_a, spec_slot="F-R1-001", status="completed")
        _insert_feature(db_b, spec_slot="F-R1-002", status="completed")

        converged, diff = check_convergence(db_a, db_b)
        assert converged is False
        assert "F-R1-001" in diff
        assert "F-R1-002" in diff

    def test_uuid_differences_do_not_cause_divergence(self, tmp_path):
        """Features with same spec_slot but different UUIDs must converge."""
        from bob.orchestrator.weekend_watchdog import check_convergence

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        for db in [db_a, db_b]:
            _init_db(db)
            # Same spec_slot, different UUIDs (fresh minted each time)
            _insert_feature(db, name="The Feature", spec_slot="F-R1-100", status="completed")

        converged, diff = check_convergence(db_a, db_b)
        assert converged is True
        assert diff == set()

    def test_pending_features_excluded_from_comparison(self, tmp_path):
        from bob.orchestrator.weekend_watchdog import check_convergence

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        _init_db(db_a)
        _init_db(db_b)
        # Only db_a has a pending feature with spec_slot
        _insert_feature(db_a, spec_slot="F-R1-001", status="pending")
        # Both are empty of completed features

        converged, diff = check_convergence(db_a, db_b)
        assert converged is True
        assert diff == set()


# ---------------------------------------------------------------------------
# bob.spawn_watchdog integration tests (import + instantiation)
# ---------------------------------------------------------------------------


class TestSpawnWatchdogIntegration:
    def test_spawn_watchdog_importable(self):
        from bob.spawn_watchdog import SpawnWatchdog
        assert SpawnWatchdog is not None

    def test_spawn_watchdog_has_expected_attributes(self):
        from bob.spawn_watchdog import SpawnWatchdog
        import inspect
        sig = inspect.signature(SpawnWatchdog.__init__)
        assert "proc" in sig.parameters
        assert "feature_id" in sig.parameters
        assert "timeout_s" in sig.parameters

    def test_spawn_watchdog_module_importable(self):
        import bob.spawn_watchdog as sw
        assert hasattr(sw, "SpawnWatchdog")
        assert hasattr(sw, "_DEFAULT_TIMEOUT_S")
        assert hasattr(sw, "_DEFAULT_HEARTBEAT_INTERVAL_S")

"""Tests for bob.convergence.check_convergence."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                workspace_path TEXT NOT NULL DEFAULT '/tmp/test',
                status TEXT NOT NULL DEFAULT 'planning',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                acceptance_criteria TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                spec_slot TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _add_features(db_path: Path, slots: list[str], status: str = "completed") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (pid, "test-project"),
        )
        for slot in slots:
            conn.execute(
                "INSERT INTO features (id, project_id, name, spec_slot, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), pid, f"Feature {slot}", slot, status),
            )
        conn.commit()
    finally:
        conn.close()


def test_check_convergence_identical_slots_converge(tmp_path):
    """Same spec_slot sets in two DBs → converged=True."""
    from bob.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    _add_features(db_a, ["F-R1-100", "F-R1-200"])
    _add_features(db_b, ["F-R1-100", "F-R1-200"])

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_different_slots_diverge(tmp_path):
    """Different spec_slot sets → converged=False with non-empty diff."""
    from bob.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    _add_features(db_a, ["F-R1-100"])
    _add_features(db_b, ["F-R1-999"])

    converged, diff = check_convergence(db_a, db_b)
    assert converged is False
    assert "F-R1-100" in diff or "F-R1-999" in diff


def test_check_convergence_empty_dbs_converge(tmp_path):
    """Two empty databases → converged (nothing to differ on)."""
    from bob.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_returns_tuple(tmp_path):
    """Function must return (bool, set) tuple."""
    from bob.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)

    result = check_convergence(db_a, db_b)
    assert isinstance(result, tuple)
    assert len(result) == 2
    converged, diff = result
    assert isinstance(converged, bool)
    assert isinstance(diff, set)


def test_check_convergence_excludes_non_completed(tmp_path):
    """Pending/failed features must not affect convergence."""
    from bob.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    _add_features(db_a, ["F-R1-100"], status="completed")
    _add_features(db_a, ["F-R1-200"], status="pending")
    _add_features(db_b, ["F-R1-100"], status="completed")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True, f"Pending feature leaked into diff: {diff}"


def test_check_convergence_excludes_null_spec_slot(tmp_path):
    """Features with NULL spec_slot must be excluded from comparison."""
    from bob.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)

    # Insert features with NULL spec_slot in both DBs
    for db in [db_a, db_b]:
        conn = sqlite3.connect(str(db))
        pid = str(uuid.uuid4())
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)", (pid, "p"))
        conn.execute(
            "INSERT INTO features (id, project_id, name, spec_slot, status) "
            "VALUES (?, ?, 'no-slot-feature', NULL, 'completed')",
            (str(uuid.uuid4()), pid),
        )
        conn.commit()
        conn.close()

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()

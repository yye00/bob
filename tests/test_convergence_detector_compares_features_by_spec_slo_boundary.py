"""Boundary-case tests for check_convergence: empty/zero/minimum inputs.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest


def _init_db(db_path: Path) -> None:
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


def test_boundary_two_empty_databases_return_converged(tmp_path):
    """Two empty databases must return (True, set()) without raising."""
    from bob3.convergence import check_convergence

    db_a = tmp_path / "empty_a.db"
    db_b = tmp_path / "empty_b.db"
    _init_db(db_a)
    _init_db(db_b)

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_boundary_single_feature_each_matching(tmp_path):
    """Minimum non-trivial input: one matching spec_slot in each DB."""
    from bob3.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    for db in [db_a, db_b]:
        _init_db(db)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), "Min feature", "F-R1-001", "completed"),
        )
        conn.commit()
        conn.close()

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_boundary_all_null_spec_slots_returns_converged(tmp_path):
    """DBs with only NULL spec_slot features return (True, set()) — not an error."""
    from bob3.convergence import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    for db in [db_a, db_b]:
        _init_db(db)
        conn = sqlite3.connect(str(db))
        for i in range(3):
            conn.execute(
                "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, NULL, ?)",
                (str(uuid.uuid4()), f"Feature {i}", "completed"),
            )
        conn.commit()
        conn.close()

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_boundary_one_empty_one_with_features(tmp_path):
    """One empty DB vs one with features returns well-defined (False, diff)."""
    from bob3.convergence import check_convergence

    db_a = tmp_path / "empty.db"
    db_b = tmp_path / "with_features.db"
    _init_db(db_a)
    _init_db(db_b)

    conn = sqlite3.connect(str(db_b))
    conn.execute(
        "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), "Feature X", "F-R1-100", "completed"),
    )
    conn.commit()
    conn.close()

    converged, diff = check_convergence(db_a, db_b)
    assert converged is False
    assert "F-R1-100" in diff


def test_boundary_no_spec_slot_column_returns_converged(tmp_path):
    """Databases without spec_slot column return (True, set()) — graceful handling."""
    from bob3.convergence import check_convergence

    db_a = tmp_path / "old_a.db"
    db_b = tmp_path / "old_b.db"
    for db in [db_a, db_b]:
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE features (id TEXT PRIMARY KEY, name TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO features VALUES (?, ?, ?)",
            (str(uuid.uuid4()), "Old feature", "completed"),
        )
        conn.commit()
        conn.close()

    # Must not raise — returns (True, set()) because no spec_slots exist
    converged, diff = check_convergence(db_a, db_b)
    assert isinstance(converged, bool)
    assert isinstance(diff, set)

"""Tests for bob3.weekend_watchdog.check_convergence.

Verifies that check_convergence compares feature sets by spec_slot
(stable YAML key) rather than by UUID (minted fresh on every bob3 init).
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


def _insert_feature(db_path: Path, name: str, spec_slot: str, status: str = "completed") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), name, spec_slot, status),
        )
        conn.commit()
    finally:
        conn.close()


def test_check_convergence_is_importable():
    """check_convergence must be importable from bob3.weekend_watchdog."""
    from bob3.weekend_watchdog import check_convergence  # noqa: F401

    assert callable(check_convergence)


def test_check_convergence_converged_by_spec_slot(tmp_path):
    """Two DBs with matching spec_slots must return converged=True even with different UUIDs."""
    from bob3.weekend_watchdog import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    _insert_feature(db_a, "Feature Alpha", "F-R1-001")
    _insert_feature(db_b, "Feature Alpha", "F-R1-001")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_diverged_by_spec_slot(tmp_path):
    """Two DBs with different spec_slots must return converged=False."""
    from bob3.weekend_watchdog import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    _insert_feature(db_a, "Feature A", "F-R1-001")
    _insert_feature(db_b, "Feature B", "F-R1-002")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is False
    assert "F-R1-001" in diff
    assert "F-R1-002" in diff


def test_check_convergence_ignores_uuid_churn(tmp_path):
    """Same spec_slot with different UUIDs must still converge (UUID churn is irrelevant)."""
    from bob3.weekend_watchdog import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    # Each DB has a different UUID but the same spec_slot
    _insert_feature(db_a, "Feature X", "F-R3-100")
    _insert_feature(db_b, "Feature X (renamed copy)", "F-R3-100")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_excludes_non_completed(tmp_path):
    """Only completed features should be included in the comparison."""
    from bob3.weekend_watchdog import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    # db_a has F-R1-001 completed and F-R1-002 in-progress
    _insert_feature(db_a, "Done feature", "F-R1-001", status="completed")
    _insert_feature(db_a, "In-progress", "F-R1-002", status="executing")
    # db_b only has F-R1-001
    _insert_feature(db_b, "Done feature", "F-R1-001", status="completed")

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_excludes_null_spec_slots(tmp_path):
    """Features with NULL spec_slot must be excluded from convergence comparison."""
    from bob3.weekend_watchdog import check_convergence

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _init_db(db_a)
    _init_db(db_b)
    conn_a = sqlite3.connect(str(db_a))
    conn_a.execute(
        "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, NULL, ?)",
        (str(uuid.uuid4()), "No slot", "completed"),
    )
    conn_a.commit()
    conn_a.close()

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True
    assert diff == set()


def test_check_convergence_returns_tuple(tmp_path):
    """check_convergence must return a (bool, set) tuple."""
    from bob3.weekend_watchdog import check_convergence

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


def test_check_convergence_by_spec_slot(tmp_path):
    """check_convergence must compare features by spec_slot, not by UUID.

    Two generations with the same spec_slots but entirely different UUIDs must
    be reported as converged. This is the core correctness test for the feature:
    UUID churn across bob3 init calls must not prevent convergence detection.
    """
    from bob3.weekend_watchdog import check_convergence

    db_a = tmp_path / "gen1.db"
    db_b = tmp_path / "gen2.db"
    _init_db(db_a)
    _init_db(db_b)

    # Both generations implement the same spec features, but with fresh UUIDs.
    # UUID-based comparison would produce 100% diff; spec_slot-based comparison
    # must produce 0% diff (converged).
    slots = ["F-R1-001", "F-R1-002", "F-R2-010"]
    for slot in slots:
        _insert_feature(db_a, f"Feature {slot} (gen1)", slot)
        _insert_feature(db_b, f"Feature {slot} (gen2)", slot)

    converged, diff = check_convergence(db_a, db_b)
    assert converged is True, f"Expected converged=True but got diff={diff!r}"
    assert diff == set()

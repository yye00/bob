"""Tests that convergence_checker uses feature name, not UUID id, for comparison."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob.orchestrator.convergence_checker import (
    ConvergenceResult,
    check_three_gens,
    compare_by_name,
)


def _make_db(path: Path, rows: list[tuple[str, str]]) -> None:
    """rows = [(id, name)] with status='completed'."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE features (id TEXT, name TEXT, status TEXT, needs_human INTEGER DEFAULT 0)"
    )
    for uid, name in rows:
        conn.execute("INSERT INTO features VALUES (?, ?, 'completed', 0)", (uid, name))
    conn.commit()
    conn.close()


def test_compare_by_name_returns_names_not_uuids():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        _make_db(db, [("uuid-1", "feature-alpha"), ("uuid-2", "feature-beta")])
        names = compare_by_name(db)
    assert "feature-alpha" in names
    assert "feature-beta" in names
    assert "uuid-1" not in names
    assert "uuid-2" not in names


def test_same_features_different_uuids_converges():
    """Convergence must hold when UUIDs differ but names match (fresh init scenario)."""
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "g2.db"
        # Same names, completely different UUIDs (simulates bob init minting new IDs)
        _make_db(d0, [("aaaa", "feat-x"), ("bbbb", "feat-y")])
        _make_db(d1, [("cccc", "feat-x"), ("dddd", "feat-y")])
        _make_db(d2, [("eeee", "feat-x"), ("ffff", "feat-y")])
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.CONVERGED


def test_different_names_does_not_converge():
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "g2.db"
        _make_db(d0, [("uuid-a", "feat-x")])
        _make_db(d1, [("uuid-b", "feat-y")])  # different name
        _make_db(d2, [("uuid-c", "feat-x")])
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.NOT_CONVERGED

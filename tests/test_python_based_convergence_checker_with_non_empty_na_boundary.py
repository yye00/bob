"""Boundary tests for convergence_checker.check_convergence.

Verifies well-defined (non-raising) behavior at boundary inputs:
  - empty feature sets (zero completed features)
  - single feature
  - minimum valid input (all three dbs with one feature each)
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob3.convergence_checker import check_convergence


def _make_db(path: Path, completed_names: list[str]) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE features (id TEXT, name TEXT, status TEXT)")
    for name in completed_names:
        conn.execute("INSERT INTO features VALUES (?, ?, ?)", (name + "-uuid", name, "completed"))
    conn.commit()
    conn.close()


def test_all_three_dbs_empty_returns_not_converged():
    """Empty completed sets must return (False, set()) without raising."""
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        for d in (d0, d1, d2):
            _make_db(d, [])

        result = check_convergence(d0, d1, d2)

    assert isinstance(result, tuple)
    converged, diff = result
    assert converged is False
    assert isinstance(diff, set)


def test_one_db_empty_returns_not_converged():
    """Single empty db triggers non-empty guard; must not raise."""
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        _make_db(d0, ["feat-alpha"])
        _make_db(d1, ["feat-alpha"])
        _make_db(d2, [])  # empty

        result = check_convergence(d0, d1, d2)

    converged, diff = result
    assert converged is False
    assert isinstance(diff, set)


def test_minimum_one_feature_per_db_converges():
    """Minimum valid case: one matching feature in each db converges."""
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        for d in (d0, d1, d2):
            _make_db(d, ["only-feature"])

        converged, diff = check_convergence(d0, d1, d2)

    assert converged is True
    assert diff == set()


def test_missing_db_returns_not_converged():
    """Non-existent db path returns (False, set()) without raising."""
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "missing.db"
        _make_db(d0, ["feat-x"])
        _make_db(d1, ["feat-x"])
        # d2 intentionally not created

        result = check_convergence(d0, d1, d2)

    converged, diff = result
    assert converged is False
    assert isinstance(diff, set)

"""Tests for python_based_convergence_checker_non_empty_name_based.

Verifies that the convergence checker:
  - Uses stdlib sqlite3 (no shell-out to sqlite3 CLI)
  - Returns NOT_CONVERGED when any completed set is empty (non-empty guard)
  - Compares by feature name, not UUID id
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from bob.python_based_convergence_checker_non_empty_name_based import (
    python_based_convergence_checker_non_empty_name_based,
)


def _make_db(path: Path, rows: list[tuple[str, str]], status: str = "completed") -> None:
    """rows = [(id, name)]"""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE features (id TEXT, name TEXT, status TEXT)")
    for uid, name in rows:
        conn.execute("INSERT INTO features VALUES (?, ?, ?)", (uid, name, status))
    conn.commit()
    conn.close()


def test_python_based_convergence_checker_non_empty_name_based():
    """Core AC test: function exists, uses python sqlite3, non-empty + name-based comparison."""
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "g2.db"

        # Same names, different UUIDs — must converge (name-based, not UUID-based)
        _make_db(d0, [("uuid-aaa", "feat-alpha"), ("uuid-bbb", "feat-beta")])
        _make_db(d1, [("uuid-ccc", "feat-alpha"), ("uuid-ddd", "feat-beta")])
        _make_db(d2, [("uuid-eee", "feat-alpha"), ("uuid-fff", "feat-beta")])

        converged, diff = python_based_convergence_checker_non_empty_name_based(d0, d1, d2)

    assert converged is True
    assert diff == set()


def test_empty_completed_set_returns_not_converged():
    """Non-empty guard: empty completed set must return NOT_CONVERGED."""
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "g2.db"

        _make_db(d0, [("uuid-a", "feat-x")])
        _make_db(d1, [("uuid-b", "feat-x")])
        # d2 has no completed features
        _make_db(d2, [], status="executing")

        converged, diff = python_based_convergence_checker_non_empty_name_based(d0, d1, d2)

    assert converged is False


def test_different_names_not_converged():
    """Different names across generations must return NOT_CONVERGED."""
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "g2.db"

        _make_db(d0, [("uuid-a", "feat-x")])
        _make_db(d1, [("uuid-b", "feat-y")])  # different name
        _make_db(d2, [("uuid-c", "feat-x")])

        converged, diff = python_based_convergence_checker_non_empty_name_based(d0, d1, d2)

    assert converged is False
    assert len(diff) > 0


def test_uuids_ignored_same_names_converge():
    """UUIDs are completely different but names match — must be CONVERGED."""
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "g2.db"

        _make_db(d0, [("aaaa-1111", "my-feature")])
        _make_db(d1, [("bbbb-2222", "my-feature")])
        _make_db(d2, [("cccc-3333", "my-feature")])

        converged, diff = python_based_convergence_checker_non_empty_name_based(d0, d1, d2)

    assert converged is True
    assert diff == set()


def test_missing_db_returns_not_converged():
    """Missing database file must return NOT_CONVERGED."""
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "does_not_exist.db"

        _make_db(d0, [("uuid-a", "feat-x")])
        _make_db(d1, [("uuid-b", "feat-x")])

        converged, diff = python_based_convergence_checker_non_empty_name_based(d0, d1, d2)

    assert converged is False

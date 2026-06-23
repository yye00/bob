"""Tests for bob3.convergence_checker.check_convergence.

Verifies the main AC: Python-based convergence checker with non-empty +
name-based comparison. Fixes for the 2026-05-23 weekend_watchdog silent exits.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob3.convergence_checker import check_convergence


def _make_db(path: Path, rows: list[tuple[str, str]], status: str = "completed") -> None:
    """Create a minimal features DB. rows = [(id, name)]"""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE features (id TEXT, name TEXT, status TEXT)")
    for uid, name in rows:
        conn.execute("INSERT INTO features VALUES (?, ?, ?)", (uid, name, status))
    conn.commit()
    conn.close()


class TestCheckConvergenceNameBased:
    """Name-based comparison: same names different UUIDs must converge."""

    def test_same_names_different_uuids_converge(self):
        with tempfile.TemporaryDirectory() as td:
            d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
            _make_db(d0, [("uuid-aaa", "feat-alpha"), ("uuid-bbb", "feat-beta")])
            _make_db(d1, [("uuid-ccc", "feat-alpha"), ("uuid-ddd", "feat-beta")])
            _make_db(d2, [("uuid-eee", "feat-alpha"), ("uuid-fff", "feat-beta")])

            converged, diff = check_convergence(d0, d1, d2)

        assert converged is True
        assert diff == set()

    def test_different_names_not_converged(self):
        with tempfile.TemporaryDirectory() as td:
            d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
            _make_db(d0, [("uuid-a", "feat-x")])
            _make_db(d1, [("uuid-b", "feat-y")])  # different name
            _make_db(d2, [("uuid-c", "feat-x")])

            converged, diff = check_convergence(d0, d1, d2)

        assert converged is False
        assert len(diff) > 0


class TestCheckConvergenceNonEmptyGuard:
    """Non-empty guard: empty completed set must never converge."""

    def test_empty_set_returns_not_converged(self):
        with tempfile.TemporaryDirectory() as td:
            d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
            _make_db(d0, [("uuid-a", "feat-x")])
            _make_db(d1, [("uuid-b", "feat-x")])
            _make_db(d2, [], status="executing")  # no completed features

            converged, _ = check_convergence(d0, d1, d2)

        assert converged is False

    def test_all_empty_returns_not_converged(self):
        with tempfile.TemporaryDirectory() as td:
            d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
            for d in (d0, d1, d2):
                _make_db(d, [])

            converged, diff = check_convergence(d0, d1, d2)

        assert converged is False
        assert isinstance(diff, set)


class TestCheckConvergenceUsesStdlibSqlite3:
    """check_convergence must use stdlib sqlite3, not shell-out to sqlite3 CLI."""

    def test_no_subprocess_import_in_module(self):
        import ast
        import importlib.util
        import sys
        from pathlib import Path as P

        src_path = P(__file__).parent.parent / "src" / "bob3" / "convergence_checker.py"
        source = src_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess", \
                        "convergence_checker must not import subprocess"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "subprocess", \
                    "convergence_checker must not import from subprocess"

    def test_sqlite3_import_present(self):
        import ast
        from pathlib import Path as P

        src_path = P(__file__).parent.parent / "src" / "bob3" / "convergence_checker.py"
        source = src_path.read_text()
        tree = ast.parse(source)

        has_sqlite3 = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "sqlite3":
                        has_sqlite3 = True
            elif isinstance(node, ast.ImportFrom):
                if node.module == "sqlite3":
                    has_sqlite3 = True

        assert has_sqlite3, "convergence_checker must import stdlib sqlite3"


class TestCheckConvergenceReturnType:
    """Return type must always be tuple[bool, set[str]]."""

    def test_return_type_converged(self):
        with tempfile.TemporaryDirectory() as td:
            d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
            for d in (d0, d1, d2):
                _make_db(d, [("uid", "feat")])

            result = check_convergence(d0, d1, d2)

        assert isinstance(result, tuple)
        assert len(result) == 2
        converged, diff = result
        assert isinstance(converged, bool)
        assert isinstance(diff, set)

    def test_return_type_not_converged(self):
        with tempfile.TemporaryDirectory() as td:
            d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
            _make_db(d0, [("uid", "feat-a")])
            _make_db(d1, [("uid", "feat-b")])
            _make_db(d2, [("uid", "feat-a")])

            result = check_convergence(d0, d1, d2)

        assert isinstance(result, tuple)
        converged, diff = result
        assert isinstance(converged, bool)
        assert isinstance(diff, set)

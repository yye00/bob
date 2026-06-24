"""Error-path tests for convergence_checker.check_convergence.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (no false-positive convergence on bad input).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob.convergence_checker import check_convergence


def _make_db(path: Path, completed_names: list[str]) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE features (id TEXT, name TEXT, status TEXT)")
    for name in completed_names:
        conn.execute("INSERT INTO features VALUES (?, ?, ?)", (name + "-uuid", name, "completed"))
    conn.commit()
    conn.close()


def test_none_path_raises_value_error():
    """Passing None as a db path must raise ValueError."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "g0.db"
        _make_db(d, ["feat-x"])

        with pytest.raises(ValueError):
            check_convergence(None, d, d)


def test_empty_string_path_raises_value_error():
    """Passing an empty string path must raise ValueError."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "g0.db"
        _make_db(d, ["feat-x"])

        with pytest.raises(ValueError):
            check_convergence("", d, d)


def test_wrong_type_raises_value_error():
    """Passing a non-path non-string argument must raise ValueError."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "g0.db"
        _make_db(d, ["feat-x"])

        with pytest.raises(ValueError):
            check_convergence(42, d, d)


def test_invalid_input_does_not_silently_succeed():
    """Invalid input must not return converged=True (no silent success)."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "g0.db"
        _make_db(d, ["feat-x"])

        try:
            result = check_convergence(None, d, d)
            converged, _ = result
            assert converged is False, "invalid input must not silently report convergence"
        except ValueError:
            pass  # raising ValueError is the expected path

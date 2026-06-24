"""Tests that convergence_checker returns NOT_CONVERGED when any DB file is missing."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob.orchestrator.convergence_checker import (
    ConvergenceResult,
    check_three_gens,
    reject_missing_db,
)


def _make_db(path: Path, names: list[str]) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE features (id TEXT, name TEXT, status TEXT, needs_human INTEGER DEFAULT 0)"
    )
    for name in names:
        conn.execute("INSERT INTO features VALUES (?, ?, 'completed', 0)", (f"u-{name}", name))
    conn.commit()
    conn.close()


def test_reject_missing_db_when_first_missing(tmp_path):
    d0 = tmp_path / "missing.db"  # does not exist
    d1 = tmp_path / "g1.db"
    d2 = tmp_path / "g2.db"
    _make_db(d1, ["f1"])
    _make_db(d2, ["f1"])
    assert reject_missing_db(d0, d1, d2) == ConvergenceResult.NOT_CONVERGED


def test_reject_missing_db_when_second_missing(tmp_path):
    d0 = tmp_path / "g0.db"
    d1 = tmp_path / "missing.db"
    d2 = tmp_path / "g2.db"
    _make_db(d0, ["f1"])
    _make_db(d2, ["f1"])
    assert reject_missing_db(d0, d1, d2) == ConvergenceResult.NOT_CONVERGED


def test_reject_missing_db_when_third_missing(tmp_path):
    d0 = tmp_path / "g0.db"
    d1 = tmp_path / "g1.db"
    d2 = tmp_path / "missing.db"
    _make_db(d0, ["f1"])
    _make_db(d1, ["f1"])
    assert reject_missing_db(d0, d1, d2) == ConvergenceResult.NOT_CONVERGED


def test_reject_missing_db_returns_none_when_all_present(tmp_path):
    d0, d1, d2 = tmp_path / "g0.db", tmp_path / "g1.db", tmp_path / "g2.db"
    for d in (d0, d1, d2):
        _make_db(d, ["f1"])
    assert reject_missing_db(d0, d1, d2) is None


def test_check_three_gens_not_converged_when_db_missing():
    with tempfile.TemporaryDirectory() as td:
        d0 = Path(td) / "g0.db"
        d1 = Path(td) / "g1.db"
        d2 = Path(td) / "nonexistent.db"
        _make_db(d0, ["feat-a"])
        _make_db(d1, ["feat-a"])
        # d2 never created
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.NOT_CONVERGED

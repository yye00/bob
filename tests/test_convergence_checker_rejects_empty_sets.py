"""Tests that convergence_checker returns NOT_CONVERGED when any completed set is empty."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob.orchestrator.convergence_checker import (
    ConvergenceResult,
    check_three_gens,
    reject_empty_completed_set,
)


def _make_db(path: Path, names: list[str], status: str = "completed") -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE features (id TEXT, name TEXT, status TEXT, needs_human INTEGER DEFAULT 0)"
    )
    for name in names:
        conn.execute(
            "INSERT INTO features VALUES (?, ?, ?, 0)",
            (f"uuid-{name}", name, status),
        )
    conn.commit()
    conn.close()


def test_reject_empty_completed_set_returns_not_converged_when_c0_empty():
    assert reject_empty_completed_set(set(), {"f1"}, {"f1"}) == ConvergenceResult.NOT_CONVERGED


def test_reject_empty_completed_set_returns_not_converged_when_c1_empty():
    assert reject_empty_completed_set({"f1"}, set(), {"f1"}) == ConvergenceResult.NOT_CONVERGED


def test_reject_empty_completed_set_returns_not_converged_when_c2_empty():
    assert reject_empty_completed_set({"f1"}, {"f1"}, set()) == ConvergenceResult.NOT_CONVERGED


def test_reject_empty_completed_set_returns_none_when_all_nonempty():
    assert reject_empty_completed_set({"f1"}, {"f1"}, {"f1"}) is None


def test_check_three_gens_not_converged_when_one_db_has_no_completed():
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        _make_db(d0, ["feat-a"])
        _make_db(d1, ["feat-a"])
        _make_db(d2, [], status="completed")  # empty completed set
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.NOT_CONVERGED


def test_check_three_gens_not_converged_when_all_dbs_empty():
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        for d in (d0, d1, d2):
            _make_db(d, [])
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.NOT_CONVERGED

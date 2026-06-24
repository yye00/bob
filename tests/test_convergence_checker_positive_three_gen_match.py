"""Tests for positive (CONVERGED) case when all three gens have matching feature names."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from bob3.orchestrator.convergence_checker import (
    ConvergenceResult,
    check_three_gens,
    completed_sets_match,
    has_nonempty_completion,
    needs_human_sets_match,
)


def _make_db(
    path: Path,
    completed: list[str],
    needs_human: list[str] | None = None,
) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE features (id TEXT, name TEXT, status TEXT, needs_human INTEGER DEFAULT 0)"
    )
    for name in completed:
        conn.execute("INSERT INTO features VALUES (?, ?, 'completed', 0)", (f"u-{name}", name))
    for name in (needs_human or []):
        conn.execute("INSERT INTO features VALUES (?, ?, 'needs_human', 1)", (f"nh-{name}", name))
    conn.commit()
    conn.close()


def test_check_three_gens_converged_single_feature():
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        for d in (d0, d1, d2):
            _make_db(d, ["feat-alpha"])
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.CONVERGED


def test_check_three_gens_converged_multiple_features():
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        feats = ["feat-a", "feat-b", "feat-c"]
        for d in (d0, d1, d2):
            _make_db(d, feats)
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.CONVERGED


def test_completed_sets_match_true_when_equal():
    assert completed_sets_match({"a", "b"}, {"a", "b"}, {"a", "b"}) is True


def test_completed_sets_match_false_when_differ():
    assert completed_sets_match({"a", "b"}, {"a", "c"}, {"a", "b"}) is False


def test_has_nonempty_completion_true_when_c2_nonempty():
    assert has_nonempty_completion({"feat-a"}) is True


def test_has_nonempty_completion_false_when_c2_empty():
    assert has_nonempty_completion(set()) is False


def test_needs_human_sets_match_true_when_equal():
    assert needs_human_sets_match({"h1"}, {"h1"}, {"h1"}) is True


def test_needs_human_sets_match_false_when_differ():
    assert needs_human_sets_match({"h1"}, {"h2"}, {"h1"}) is False


def test_needs_human_sets_match_true_when_all_empty():
    assert needs_human_sets_match(set(), set(), set()) is True


def test_check_three_gens_not_converged_when_one_gen_has_extra_feature():
    with tempfile.TemporaryDirectory() as td:
        d0, d1, d2 = Path(td) / "g0.db", Path(td) / "g1.db", Path(td) / "g2.db"
        _make_db(d0, ["feat-a", "feat-b"])
        _make_db(d1, ["feat-a"])  # missing feat-b
        _make_db(d2, ["feat-a", "feat-b"])
        result = check_three_gens(d0, d1, d2)
    assert result == ConvergenceResult.NOT_CONVERGED

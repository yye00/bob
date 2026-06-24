"""Tests that write_convergence_achieved_json writes CONVERGENCE_ACHIEVED.json correctly."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob.orchestrator.convergence_checker import (
    ConvergenceResult,
    check_three_gens,
    write_convergence_achieved_json,
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


def test_write_convergence_achieved_json_creates_file(tmp_path):
    names = {"feat-a", "feat-b"}
    out = tmp_path / "CONVERGENCE_ACHIEVED.json"
    write_convergence_achieved_json(names, out)
    assert out.exists()


def test_write_convergence_achieved_json_content(tmp_path):
    names = {"feat-a", "feat-b"}
    out = tmp_path / "CONVERGENCE_ACHIEVED.json"
    write_convergence_achieved_json(names, out)
    data = json.loads(out.read_text())
    assert "completed_names" in data
    assert set(data["completed_names"]) == names


def test_write_convergence_achieved_json_has_status_field(tmp_path):
    names = {"feat-x"}
    out = tmp_path / "CONVERGENCE_ACHIEVED.json"
    write_convergence_achieved_json(names, out)
    data = json.loads(out.read_text())
    assert data.get("status") == "CONVERGED"


def test_check_three_gens_writes_json_on_convergence(tmp_path):
    d0, d1, d2 = tmp_path / "g0.db", tmp_path / "g1.db", tmp_path / "g2.db"
    for d in (d0, d1, d2):
        _make_db(d, ["feat-a", "feat-b"])
    out_path = tmp_path / "CONVERGENCE_ACHIEVED.json"
    result = check_three_gens(d0, d1, d2, output_path=out_path)
    assert result == ConvergenceResult.CONVERGED
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert set(data["completed_names"]) == {"feat-a", "feat-b"}


def test_check_three_gens_does_not_write_json_when_not_converged(tmp_path):
    d0, d1, d2 = tmp_path / "g0.db", tmp_path / "g1.db", tmp_path / "g2.db"
    _make_db(d0, ["feat-a"])
    _make_db(d1, ["feat-b"])  # different
    _make_db(d2, ["feat-a"])
    out_path = tmp_path / "CONVERGENCE_ACHIEVED.json"
    result = check_three_gens(d0, d1, d2, output_path=out_path)
    assert result == ConvergenceResult.NOT_CONVERGED
    assert not out_path.exists()

"""Tests that open_db_via_stdlib_sqlite3 uses sqlite3 module and never shells out."""

from __future__ import annotations

import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.orchestrator.convergence_checker import (
    never_invokes_sqlite3_subprocess,
    open_db_via_stdlib_sqlite3,
)


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE features (id TEXT, name TEXT, status TEXT, needs_human INTEGER DEFAULT 0)"
    )
    conn.commit()
    conn.close()


def test_never_invokes_sqlite3_subprocess_returns_true():
    assert never_invokes_sqlite3_subprocess() is True


def test_open_db_via_stdlib_sqlite3_returns_connection(tmp_path):
    db = tmp_path / "test.db"
    _make_db(db)
    conn = open_db_via_stdlib_sqlite3(db)
    assert conn is not None
    conn.close()


def test_open_db_via_stdlib_sqlite3_does_not_call_subprocess_run(tmp_path):
    db = tmp_path / "test.db"
    _make_db(db)
    with patch("subprocess.run") as mock_run, patch("subprocess.Popen") as mock_popen:
        conn = open_db_via_stdlib_sqlite3(db)
        conn.close()
        mock_run.assert_not_called()
        mock_popen.assert_not_called()


def test_open_db_returns_sqlite3_connection_type(tmp_path):
    db = tmp_path / "test.db"
    _make_db(db)
    conn = open_db_via_stdlib_sqlite3(db)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_open_db_can_query_features_table(tmp_path):
    db = tmp_path / "test.db"
    conn0 = sqlite3.connect(str(db))
    conn0.execute(
        "CREATE TABLE features (id TEXT, name TEXT, status TEXT, needs_human INTEGER DEFAULT 0)"
    )
    conn0.execute("INSERT INTO features VALUES ('u1', 'feat-a', 'completed', 0)")
    conn0.commit()
    conn0.close()

    conn = open_db_via_stdlib_sqlite3(db)
    rows = conn.execute("SELECT name FROM features").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "feat-a"

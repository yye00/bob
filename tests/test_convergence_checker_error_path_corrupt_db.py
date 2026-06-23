"""Tests that open_db_via_stdlib_sqlite3 raises sqlite3.DatabaseError for corrupt DB."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob3.orchestrator.convergence_checker import open_db_via_stdlib_sqlite3


def _make_corrupt_db(path: Path) -> None:
    """Create a real SQLite DB then corrupt a B-tree page to trigger 'malformed'."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE features (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO features VALUES (1, 'test')")
    conn.commit()
    conn.close()
    # Corrupt the B-tree page-type byte at offset 100 (first page interior)
    # to produce "database disk image is malformed"
    data = bytearray(path.read_bytes())
    data[100] = 0xAB  # invalid page type triggers malformed error
    path.write_bytes(bytes(data))


def test_corrupt_db_raises_database_error_with_malformed(tmp_path):
    db = tmp_path / "corrupt.db"
    _make_corrupt_db(db)
    with pytest.raises(sqlite3.DatabaseError, match="malformed"):
        conn = open_db_via_stdlib_sqlite3(db)
        conn.execute("SELECT * FROM features").fetchall()
        conn.close()

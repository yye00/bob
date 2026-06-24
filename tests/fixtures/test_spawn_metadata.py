"""Fixture helpers for spawn metadata tests.

Provides reusable helpers for creating test databases and workspaces
used by spawn-related tests across the test suite.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def make_db_with_project(
    tmp_path: Path,
    name: str,
    spec_path: str = "",
    *,
    db_name: str = "bob.db",
) -> Path:
    """Create a minimal bob.db with a single projects row.

    Args:
        tmp_path: Directory in which to create the database file.
        name: The ``projects.name`` value (simulates parent generation name
              when testing stale-name detection).
        spec_path: The ``projects.spec_path`` value. Pass a pytest tmpdir
                   path (containing "pytest-of-") to simulate a stale leak.
        db_name: Filename for the database (default: "bob.db").

    Returns:
        Path to the created database file.
    """
    db = tmp_path / db_name
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            spec_path TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO projects (id, name, spec_path) VALUES (?, ?, ?)",
        ("proj-fixture-001", name, spec_path),
    )
    conn.commit()
    conn.close()
    return db


def make_empty_db(tmp_path: Path, *, db_name: str = "bob.db") -> Path:
    """Create a bob.db with an empty projects table.

    Useful for testing the boundary case where no project rows exist.

    Args:
        tmp_path: Directory in which to create the database file.
        db_name: Filename for the database (default: "bob.db").

    Returns:
        Path to the created database file.
    """
    db = tmp_path / db_name
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            spec_path TEXT
        )"""
    )
    conn.commit()
    conn.close()
    return db


def make_workspace(tmp_path: Path, basename: str) -> Path:
    """Create a workspace directory with the given basename.

    Args:
        tmp_path: Parent directory (typically pytest's tmp_path fixture).
        basename: Directory name (simulates the generation, e.g. "bob70").

    Returns:
        Path to the created workspace directory.
    """
    workspace = tmp_path / basename
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


STALE_PYTEST_SPEC_PATH = "/tmp/pytest-of-root/pytest-42/test_session0/minimal.yaml"
CLEAN_SPEC_PATH = "/home/user/bob70/examples/bootstrap_v0.69.yaml"

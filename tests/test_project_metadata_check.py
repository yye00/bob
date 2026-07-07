"""Tests for bob.run_loop.verify_project_metadata.

Feature 1d00efac: bob init re-run after spawn fixes stale project metadata.

spawn_next_generation.sh rsync-copies the parent bob.db, which keeps the parent's
project name and can retain a spec_path that points at a pytest tmpdir. These tests
verify that verify_project_metadata detects and corrects the stale name, and warns
about a stale (pytest-of-) spec_path, returning a well-defined result each time.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob.run_loop import (
    ProjectMetadataCheckResult,
    verify_project_metadata,
)


def _make_db(
    db: Path,
    *,
    name: str = "bob89",
    spec_path: str = "",
    with_row: bool = True,
) -> Path:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT, "
        "workspace_path TEXT)"
    )
    if with_row:
        conn.execute(
            "INSERT INTO projects (id, name, spec_path, workspace_path) "
            "VALUES (?, ?, ?, ?)",
            ("proj-001", name, spec_path, str(db.parent)),
        )
    conn.commit()
    conn.close()
    return db


def _stored_name(db: Path) -> str | None:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


class TestNameCorrection:
    def test_stale_name_is_corrected_in_place(self, tmp_path):
        workspace = tmp_path / "bob90"
        workspace.mkdir()
        db = _make_db(workspace / "bob.db", name="bob89")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert result.name_was_stale is True
        assert result.corrected_name == "bob90"
        assert result.workspace_basename == "bob90"
        assert _stored_name(db) == "bob90"

    def test_matching_name_is_left_untouched(self, tmp_path):
        workspace = tmp_path / "bob90"
        workspace.mkdir()
        db = _make_db(workspace / "bob.db", name="bob90")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob90"
        assert _stored_name(db) == "bob90"


class TestSpecPathDetection:
    def test_pytest_tmpdir_spec_path_flagged_as_stale(self, tmp_path):
        workspace = tmp_path / "bob90"
        workspace.mkdir()
        db = _make_db(
            workspace / "bob.db",
            name="bob90",
            spec_path="/tmp/pytest-of-runner/pytest-3/minimal.yaml",
        )

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True
        # Name matched, so no correction, but the run still returns a result.
        assert result.name_was_stale is False

    def test_clean_spec_path_not_flagged(self, tmp_path):
        workspace = tmp_path / "bob90"
        workspace.mkdir()
        db = _make_db(
            workspace / "bob.db",
            name="bob90",
            spec_path="/home/user/bob90/examples/bootstrap.yaml",
        )

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_stale_name_and_stale_spec_path_together(self, tmp_path):
        workspace = tmp_path / "bob90"
        workspace.mkdir()
        db = _make_db(
            workspace / "bob.db",
            name="bob89",
            spec_path="/tmp/pytest-of-x/pytest-9/spec.yaml",
        )

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob90"
        assert result.spec_path_was_stale is True
        assert _stored_name(db) == "bob90"


class TestResultShape:
    def test_returns_named_tuple_with_all_fields(self, tmp_path):
        workspace = tmp_path / "bob90"
        workspace.mkdir()
        db = _make_db(workspace / "bob.db", name="bob90")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result._fields == (
            "name_was_stale",
            "spec_path_was_stale",
            "corrected_name",
            "workspace_basename",
        )

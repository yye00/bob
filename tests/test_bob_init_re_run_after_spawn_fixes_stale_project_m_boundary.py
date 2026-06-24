"""Boundary-case tests for bob init re-run after spawn fixes stale project metadata.

Tests that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions (AC5 boundary case requirement).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_db(tmp_path: Path, name: str = "bob59", spec_path: str = "") -> Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, ?)", (name, spec_path))
    conn.commit()
    conn.close()
    return db


def _make_empty_db(tmp_path: Path) -> Path:
    """DB with projects table but no rows."""
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.commit()
    conn.close()
    return db


class TestVerifyProjectMetadataBoundary:
    """verify_project_metadata returns well-defined results for edge inputs."""

    def test_empty_workspace_string_returns_result(self, tmp_path):
        """Empty string workspace is treated as cwd — no exception raised."""
        from bob.run_loop import verify_project_metadata, ProjectMetadataCheckResult

        db = _make_db(tmp_path, "bob59")
        result = verify_project_metadata(workspace="", db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert isinstance(result.name_was_stale, bool)
        assert isinstance(result.workspace_basename, str)
        assert len(result.workspace_basename) > 0

    def test_none_workspace_returns_result(self, tmp_path):
        """None workspace defaults to cwd — no exception raised."""
        from bob.run_loop import verify_project_metadata, ProjectMetadataCheckResult

        db = _make_db(tmp_path, "bob59")
        result = verify_project_metadata(workspace=None, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert isinstance(result.name_was_stale, bool)

    def test_empty_projects_table_returns_false_no_raise(self, tmp_path):
        """Empty projects table returns name_was_stale=False rather than raising."""
        from bob.run_loop import verify_project_metadata

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob60"

    def test_empty_spec_path_no_stale_flag(self, tmp_path):
        """Empty spec_path (zero-length string) does not set spec_path_was_stale."""
        from bob.run_loop import verify_project_metadata

        workspace = tmp_path / "bob59"
        workspace.mkdir()
        db = _make_db(tmp_path, "bob59", spec_path="")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_null_spec_path_no_stale_flag(self, tmp_path):
        """NULL spec_path in DB does not set spec_path_was_stale."""
        from bob.run_loop import verify_project_metadata

        workspace = tmp_path / "bob59"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, NULL)", ("bob59",))
        conn.commit()
        conn.close()

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_single_char_workspace_name_is_valid(self, tmp_path):
        """A single-character workspace name is treated as a valid basename."""
        from bob.run_loop import verify_project_metadata

        workspace = tmp_path / "x"
        workspace.mkdir()
        db = _make_db(tmp_path, "x")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.workspace_basename == "x"

    def test_name_matches_exactly_returns_not_stale(self, tmp_path):
        """Minimum mismatch: name already correct, returns not-stale immediately."""
        from bob.run_loop import verify_project_metadata

        workspace = tmp_path / "bob73"
        workspace.mkdir()
        db = _make_db(tmp_path, "bob73")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.spec_path_was_stale is False


class TestUpdateProjectNameIfMismatchBoundary:
    """update_project_name_if_mismatch boundary cases."""

    def test_empty_table_returns_false(self, tmp_path):
        from bob.orchestrator.project_metadata_check import update_project_name_if_mismatch

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)

        result = update_project_name_if_mismatch(db_path=db, workspace=workspace)
        assert result is False

    def test_already_correct_returns_false(self, tmp_path):
        from bob.orchestrator.project_metadata_check import update_project_name_if_mismatch

        workspace = tmp_path / "bob59"
        workspace.mkdir()
        db = _make_db(tmp_path, "bob59")

        result = update_project_name_if_mismatch(db_path=db, workspace=workspace)
        assert result is False


class TestRejectPytestTmpdirBoundary:
    """reject_pytest_tmpdir_in_spec_path boundary cases."""

    def test_no_rows_no_raise(self, tmp_path):
        from bob.orchestrator.project_metadata_check import reject_pytest_tmpdir_in_spec_path

        db = _make_empty_db(tmp_path)
        reject_pytest_tmpdir_in_spec_path(db_path=db)

    def test_empty_spec_path_no_raise(self, tmp_path):
        from bob.orchestrator.project_metadata_check import reject_pytest_tmpdir_in_spec_path

        db = _make_db(tmp_path, "bob59", spec_path="")
        reject_pytest_tmpdir_in_spec_path(db_path=db)

    def test_none_spec_path_no_raise(self, tmp_path):
        from bob.orchestrator.project_metadata_check import reject_pytest_tmpdir_in_spec_path

        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, NULL)", ("bob59",))
        conn.commit()
        conn.close()

        reject_pytest_tmpdir_in_spec_path(db_path=db)

"""Tests for bob.spawn_reinit_guard.verify_project_metadata.

The spawn_reinit_guard module provides a startup check that detects and
corrects stale project metadata introduced when spawn_next_generation.sh
rsync-copies the parent bob.db without re-running bob init.
"""

from __future__ import annotations

import sqlite3
import pathlib

import pytest


def _make_db(tmp_path: pathlib.Path, name: str, spec_path: str = "") -> pathlib.Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, ?)", (name, spec_path))
    conn.commit()
    conn.close()
    return db


def _make_empty_db(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.commit()
    conn.close()
    return db


class TestVerifyProjectMetadata:
    """Core behavior of bob.spawn_reinit_guard.verify_project_metadata."""

    def test_stale_name_is_detected_and_corrected(self, tmp_path):
        """DB has parent name; workspace basename is child name — stale detected."""
        from bob.spawn_reinit_guard import verify_project_metadata

        workspace = tmp_path / "bob82"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob81")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob82"
        assert result.workspace_basename == "bob82"

        # Verify DB was updated
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob82"

    def test_correct_name_returns_not_stale(self, tmp_path):
        """Name already matches workspace basename — no-op."""
        from bob.spawn_reinit_guard import verify_project_metadata

        workspace = tmp_path / "bob81"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob81")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob81"
        assert result.spec_path_was_stale is False

    def test_pytest_tmpdir_spec_path_sets_stale_flag(self, tmp_path):
        """pytest tmpdir leak in spec_path surfaces as spec_path_was_stale=True."""
        from bob.spawn_reinit_guard import verify_project_metadata

        workspace = tmp_path / "bob81"
        workspace.mkdir()
        stale_spec = "/tmp/pytest-of-runner/pytest-42/test_init_0/spec.yaml"
        db = _make_db(tmp_path, name="bob81", spec_path=stale_spec)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True

    def test_clean_spec_path_no_stale_flag(self, tmp_path):
        """Normal spec_path does not set spec_path_was_stale."""
        from bob.spawn_reinit_guard import verify_project_metadata

        workspace = tmp_path / "bob81"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob81", spec_path="/home/user/project/spec.yaml")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_empty_table_returns_false_not_stale(self, tmp_path):
        """No rows in projects table — returns name_was_stale=False, no crash."""
        from bob.spawn_reinit_guard import verify_project_metadata

        workspace = tmp_path / "bob81"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob81"

    def test_none_workspace_defaults_to_cwd(self, tmp_path):
        """None workspace uses cwd — no exception."""
        from bob.spawn_reinit_guard import verify_project_metadata

        db = _make_db(tmp_path, name="whatever")
        result = verify_project_metadata(workspace=None, db_path=db)

        assert result is not None
        assert isinstance(result.name_was_stale, bool)
        assert isinstance(result.workspace_basename, str)

    def test_invalid_workspace_type_raises_value_error(self, tmp_path):
        """Non-path workspace type raises ValueError."""
        from bob.spawn_reinit_guard import verify_project_metadata

        db = _make_db(tmp_path, name="bob81")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=999, db_path=db)  # type: ignore[arg-type]

    def test_both_name_stale_and_spec_stale(self, tmp_path):
        """Both stale name and stale spec_path reported together."""
        from bob.spawn_reinit_guard import verify_project_metadata

        workspace = tmp_path / "bob82"
        workspace.mkdir()
        stale_spec = "/tmp/pytest-of-ci/pytest-1/test_x0/spec.yaml"
        db = _make_db(tmp_path, name="bob81", spec_path=stale_spec)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.spec_path_was_stale is True
        assert result.corrected_name == "bob82"

"""Tests for bob3.init_validator.verify_project_metadata.

Verifies that the startup validator detects and corrects stale project metadata
resulting from spawn_next_generation.sh rsync-copying the parent DB without
re-running bob3 init.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob3.init_validator import verify_project_metadata, ProjectMetadataCheckResult


def _make_db(tmp_path: Path, name: str, spec_path: str = "") -> Path:
    db = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, ?)", (name, spec_path))
    conn.commit()
    conn.close()
    return db


def _make_empty_db(tmp_path: Path) -> Path:
    db = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.commit()
    conn.close()
    return db


class TestVerifyProjectMetadataModule:
    """verify_project_metadata is importable from bob3.init_validator."""

    def test_importable(self):
        from bob3.init_validator import verify_project_metadata  # noqa: F401
        assert callable(verify_project_metadata)

    def test_result_type_importable(self):
        from bob3.init_validator import ProjectMetadataCheckResult  # noqa: F401
        assert ProjectMetadataCheckResult is not None


class TestVerifyProjectMetadataCorrection:
    """Core behavior: stale names are detected and corrected."""

    def test_stale_name_is_corrected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob87")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"
        assert result.workspace_basename == "bob99"

    def test_db_is_actually_updated(self, tmp_path):
        workspace = tmp_path / "bob100"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob87")

        verify_project_metadata(workspace=workspace, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob100"

    def test_correct_name_returns_not_stale(self, tmp_path):
        workspace = tmp_path / "bob87"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob87")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None

    def test_returns_named_tuple(self, tmp_path):
        workspace = tmp_path / "bob87"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob87")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)

    def test_pytest_tmpdir_sets_spec_path_was_stale(self, tmp_path):
        workspace = tmp_path / "bob87"
        workspace.mkdir()
        stale = "/tmp/pytest-of-runner/pytest-42/test_spawn0/spec.yaml"
        db = _make_db(tmp_path, name="bob87", spec_path=stale)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True

    def test_normal_spec_path_not_stale(self, tmp_path):
        workspace = tmp_path / "bob87"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob87", spec_path="/home/user/project/spec.yaml")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_empty_table_returns_not_stale(self, tmp_path):
        workspace = tmp_path / "bob87"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None

    def test_workspace_basename_in_result(self, tmp_path):
        workspace = tmp_path / "my-project"
        workspace.mkdir()
        db = _make_db(tmp_path, name="my-project")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.workspace_basename == "my-project"

    def test_invalid_workspace_type_raises_value_error(self, tmp_path):
        db = _make_db(tmp_path, name="bob87")

        with pytest.raises(ValueError):
            verify_project_metadata(workspace=42, db_path=db)  # type: ignore[arg-type]

    def test_none_workspace_uses_cwd(self, tmp_path):
        db = _make_db(tmp_path, name="bob87")

        result = verify_project_metadata(workspace=None, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert isinstance(result.workspace_basename, str)

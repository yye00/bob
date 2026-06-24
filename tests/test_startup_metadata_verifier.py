"""Tests for bob.startup_metadata_verifier.verify_project_metadata.

Verifies that the startup check correctly detects and corrects stale project
metadata that results from spawn_next_generation.sh rsync-copying the parent DB.
"""
from __future__ import annotations

import sqlite3
import pathlib
import pytest

from bob.startup_metadata_verifier import verify_project_metadata
from bob.run_loop import ProjectMetadataCheckResult


def _create_db(path: pathlib.Path, name: str, spec_path: str = "") -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            spec_path TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO projects (id, name, spec_path) VALUES (?, ?, ?)",
        ("proj-001", name, spec_path),
    )
    conn.commit()
    conn.close()


class TestVerifyProjectMetadata:
    """Core correctness tests for verify_project_metadata."""

    def test_stale_name_is_detected_and_corrected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        _create_db(db, name="bob66")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"
        assert result.workspace_basename == "bob99"
        assert result.spec_path_was_stale is False

    def test_db_is_actually_updated_after_stale_name(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        _create_db(db, name="bob66")

        verify_project_metadata(workspace=workspace, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "bob99"

    def test_correct_name_returns_not_stale(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        _create_db(db, name="bob99")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob99"
        assert result.spec_path_was_stale is False

    def test_stale_spec_path_detected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        stale_spec = "/tmp/pytest-of-user/pytest-42/test_foo0/minimal.yaml"
        _create_db(db, name="bob99", spec_path=stale_spec)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True
        assert result.name_was_stale is False

    def test_stale_name_and_stale_spec_path_both_detected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        stale_spec = "/tmp/pytest-of-ci/pytest-1/test_spawn0/spec.yaml"
        _create_db(db, name="bob66", spec_path=stale_spec)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"
        assert result.spec_path_was_stale is True

    def test_normal_spec_path_not_stale(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        _create_db(db, name="bob99", spec_path="/home/user/dark-factory/bob99/spec.yaml")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_returns_project_metadata_check_result_namedtuple(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        _create_db(db, name="bob99")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert hasattr(result, "name_was_stale")
        assert hasattr(result, "spec_path_was_stale")
        assert hasattr(result, "corrected_name")
        assert hasattr(result, "workspace_basename")

    def test_workspace_as_string_path(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        _create_db(db, name="bob99")

        result = verify_project_metadata(workspace=str(workspace), db_path=db)

        assert result.workspace_basename == "bob99"
        assert result.name_was_stale is False


class TestVerifyProjectMetadataBoundary:
    """Boundary: empty/None workspace returns well-defined result, no exception."""

    def test_none_workspace_returns_result(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.commit()
        conn.close()

        result = verify_project_metadata(workspace=None, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert isinstance(result.name_was_stale, bool)

    def test_empty_string_workspace_returns_result(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.commit()
        conn.close()

        result = verify_project_metadata(workspace="", db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert isinstance(result.name_was_stale, bool)

    def test_empty_projects_table_returns_not_stale(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.commit()
        conn.close()

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob99"


class TestVerifyProjectMetadataErrorPath:
    """Error path: invalid types raise ValueError, no silent success."""

    def test_integer_workspace_raises_value_error(self, tmp_path):
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError):
            verify_project_metadata(workspace=42, db_path=db)  # type: ignore[arg-type]

    def test_list_workspace_raises_value_error(self, tmp_path):
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError):
            verify_project_metadata(workspace=["bob99"], db_path=db)  # type: ignore[arg-type]

    def test_dict_workspace_raises_value_error(self, tmp_path):
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError):
            verify_project_metadata(workspace={"path": "bob99"}, db_path=db)  # type: ignore[arg-type]

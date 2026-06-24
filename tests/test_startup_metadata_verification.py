"""Tests for bob3.startup.verify_project_metadata.

Verifies that the startup module exposes verify_project_metadata and that it
correctly detects and corrects stale project metadata after spawn.
"""
from __future__ import annotations

import sqlite3
import pathlib

import pytest


def _make_db(tmp_path: pathlib.Path, name: str, spec_path: str = "") -> pathlib.Path:
    db = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, ?)", (name, spec_path))
    conn.commit()
    conn.close()
    return db


class TestStartupModuleExposesVerifyProjectMetadata:
    """bob3.startup.verify_project_metadata is accessible and functional."""

    def test_importable_from_startup_module(self):
        from bob3.startup import verify_project_metadata
        assert callable(verify_project_metadata)

    def test_returns_project_metadata_check_result(self, tmp_path):
        from bob3.startup import verify_project_metadata, ProjectMetadataCheckResult

        workspace = tmp_path / "bob82"
        workspace.mkdir()
        db = _make_db(tmp_path, "bob82")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)

    def test_stale_name_corrected_at_startup(self, tmp_path):
        """Stale parent name is detected and corrected during startup check."""
        from bob3.startup import verify_project_metadata

        workspace = tmp_path / "bob82"
        workspace.mkdir()
        db = _make_db(tmp_path, "bob81")  # parent name — stale

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob82"
        assert result.workspace_basename == "bob82"

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob82"

    def test_correct_name_no_stale(self, tmp_path):
        """No update when projects.name already matches workspace basename."""
        from bob3.startup import verify_project_metadata

        workspace = tmp_path / "bob82"
        workspace.mkdir()
        db = _make_db(tmp_path, "bob82")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None

    def test_pytest_tmpdir_spec_path_flagged(self, tmp_path):
        """spec_path with pytest-of- prefix is flagged as stale at startup."""
        from bob3.startup import verify_project_metadata

        workspace = tmp_path / "bob82"
        workspace.mkdir()
        stale = "/tmp/pytest-of-runner/pytest-7/test_spawn0/spec.yaml"
        db = _make_db(tmp_path, "bob82", spec_path=stale)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True

    def test_invalid_workspace_type_raises_value_error(self, tmp_path):
        """Non-path workspace type raises ValueError."""
        from bob3.startup import verify_project_metadata

        db = _make_db(tmp_path, "bob82")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=99, db_path=db)  # type: ignore[arg-type]

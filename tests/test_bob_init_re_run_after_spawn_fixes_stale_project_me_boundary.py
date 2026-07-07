"""Boundary tests for bob.run_loop.verify_project_metadata.

Feature 1d00efac. Empty / zero / minimum inputs must return a well-defined
ProjectMetadataCheckResult rather than raising.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bob.run_loop import (
    ProjectMetadataCheckResult,
    verify_project_metadata,
)


def _make_db(db: Path, *, with_row: bool = False, name: str = "bob90") -> Path:
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
            ("proj-001", name, "", str(db.parent)),
        )
    conn.commit()
    conn.close()
    return db


def test_empty_projects_table_returns_result_without_raising(tmp_path):
    """No project row at all: nothing to correct, result is well-defined."""
    workspace = tmp_path / "bob90"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", with_row=False)

    result = verify_project_metadata(workspace=workspace, db_path=db)

    assert isinstance(result, ProjectMetadataCheckResult)
    assert result.name_was_stale is False
    assert result.spec_path_was_stale is False
    assert result.corrected_name is None
    assert result.workspace_basename == "bob90"


def test_empty_string_workspace_falls_back_to_cwd(tmp_path, monkeypatch):
    """An empty-string workspace is a boundary no-op: treated as cwd, no raise."""
    workspace = tmp_path / "bob90"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", with_row=True, name="bob90")
    monkeypatch.chdir(workspace)

    result = verify_project_metadata(workspace="", db_path=db)

    assert isinstance(result, ProjectMetadataCheckResult)
    assert result.workspace_basename == "bob90"
    assert result.name_was_stale is False


def test_none_workspace_defaults_to_cwd(tmp_path, monkeypatch):
    """None workspace (the default) resolves to cwd and returns a result."""
    workspace = tmp_path / "bob90"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", with_row=True, name="bob90")
    monkeypatch.chdir(workspace)

    result = verify_project_metadata(workspace=None, db_path=db)

    assert isinstance(result, ProjectMetadataCheckResult)
    assert result.workspace_basename == "bob90"


def test_empty_spec_path_is_not_flagged(tmp_path):
    """An empty spec_path is a boundary value — not a pytest tmpdir leak."""
    workspace = tmp_path / "bob90"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", with_row=True, name="bob90")

    result = verify_project_metadata(workspace=workspace, db_path=db)

    assert result.spec_path_was_stale is False

"""Tests for feature a1fd6d35: bob init re-run after spawn fixes stale metadata.

Verifies src/bob/spawn_metadata_check.py:
  - verify_project_name_matches_workspace(...) -> bool
  - reinit_stale_project_metadata(...) -> ProjectMetadataCheckResult

spawn_next_generation.sh rsync-copies the parent bob.db without re-running
``bob init``. That leaves ``projects.name`` reflecting the parent generation
and ``spec_path`` possibly pointing at a pytest tmpdir. These functions detect
and correct that state at run_loop startup.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob.run_loop import ProjectMetadataCheckResult
from bob.spawn_metadata_check import (
    reinit_stale_project_metadata,
    verify_project_name_matches_workspace,
)


def _make_db(db: Path, *, name: str = "bob90", spec_path: str = "") -> Path:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT, "
        "workspace_path TEXT)"
    )
    conn.execute(
        "INSERT INTO projects (id, name, spec_path, workspace_path) "
        "VALUES (?, ?, ?, ?)",
        ("proj-001", name, spec_path, str(db.parent)),
    )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# verify_project_name_matches_workspace
# ---------------------------------------------------------------------------

def test_matching_name_returns_true(tmp_path):
    workspace = tmp_path / "bob97"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", name="bob97")

    assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is True


def test_stale_name_returns_false(tmp_path):
    """Parent-gen name still in the rsync-copied DB → mismatch detected."""
    workspace = tmp_path / "bob97"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", name="bob96")

    assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is False


# ---------------------------------------------------------------------------
# reinit_stale_project_metadata
# ---------------------------------------------------------------------------

def test_reinit_corrects_stale_name(tmp_path):
    workspace = tmp_path / "bob97"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", name="bob96")

    result = reinit_stale_project_metadata(workspace=workspace, db_path=db)

    assert isinstance(result, ProjectMetadataCheckResult)
    assert result.name_was_stale is True
    assert result.corrected_name == "bob97"
    assert result.workspace_basename == "bob97"

    # Correction persisted, and the name now matches.
    conn = sqlite3.connect(str(db))
    try:
        stored = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert stored == "bob97"
    assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is True


def test_reinit_noop_when_name_correct(tmp_path):
    workspace = tmp_path / "bob97"
    workspace.mkdir()
    db = _make_db(workspace / "bob.db", name="bob97")

    result = reinit_stale_project_metadata(workspace=workspace, db_path=db)

    assert result.name_was_stale is False
    assert result.corrected_name is None
    assert result.workspace_basename == "bob97"


def test_reinit_flags_pytest_tmpdir_spec_path(tmp_path):
    """A pytest tmpdir leak in spec_path is reported (not silently kept)."""
    workspace = tmp_path / "bob97"
    workspace.mkdir()
    db = _make_db(
        workspace / "bob.db",
        name="bob97",
        spec_path="/tmp/pytest-of-user/pytest-3/minimal.yaml",
    )

    result = reinit_stale_project_metadata(workspace=workspace, db_path=db)

    assert result.spec_path_was_stale is True


# ---------------------------------------------------------------------------
# Boundary
# ---------------------------------------------------------------------------

def test_empty_projects_table_is_welldefined(tmp_path):
    workspace = tmp_path / "bob97"
    workspace.mkdir()
    db = workspace / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "spec_path TEXT, workspace_path TEXT)"
    )
    conn.commit()
    conn.close()

    result = reinit_stale_project_metadata(workspace=workspace, db_path=db)
    assert result.name_was_stale is False
    assert result.corrected_name is None
    # No row → verify returns False (nothing matches an absent name).
    assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is False


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_workspace", [123, 12.5, ["bob97"], {"w": "x"}, object()])
def test_reinit_invalid_workspace_type_raises(bad_workspace):
    with pytest.raises(ValueError, match="workspace must be"):
        reinit_stale_project_metadata(workspace=bad_workspace)


@pytest.mark.parametrize("bad_workspace", [123, 12.5, ["bob97"]])
def test_verify_invalid_workspace_type_raises(bad_workspace):
    with pytest.raises(ValueError, match="workspace must be"):
        verify_project_name_matches_workspace(workspace=bad_workspace)


# ---------------------------------------------------------------------------
# integration: bob.run_loop
# ---------------------------------------------------------------------------

def test_delegates_to_run_loop_result_type():
    import bob.run_loop as rl

    assert hasattr(rl, "verify_project_metadata")
    assert rl.ProjectMetadataCheckResult is ProjectMetadataCheckResult
